from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "codex-profile"
CONFIG_TEMPLATE = '''# this comment must survive updates
model_provider = "OpenAI"
model = "gpt-test"

[model_providers.OpenAI]
name = "OpenAI"
base_url = "{base_url}"
wire_api = "responses"
requires_openai_auth = true

[features]
memories = true
'''
TEST_SECRETS = {
    "sk-test-original",
    "sk-test-proxy",
    "sk-test-edited",
    "sk-test-manual",
}


class CodexProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="codex-profile-test-")
        self.home = Path(self.temp_dir.name)
        self.write_live("https://original.example/v1", "sk-test-original")
        os.chmod(self.home / "auth.json", 0o664)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_live(self, base_url: str, api_key: str) -> None:
        (self.home / "config.toml").write_text(
            CONFIG_TEMPLATE.format(base_url=base_url),
            encoding="utf-8",
        )
        (self.home / "auth.json").write_text(
            json.dumps({"OPENAI_API_KEY": api_key, "other": "preserved"}),
            encoding="utf-8",
        )

    def run_cli(
        self,
        *args: str,
        input_text: str | None = None,
        expected: int = 0,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--codex-home", str(self.home), *args],
            input=input_text,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        combined = result.stdout + result.stderr
        for secret in TEST_SECRETS:
            self.assertNotIn(secret, combined)
        return result

    def load_registry(self) -> dict:
        return json.loads((self.home / "provider-profiles.json").read_text())

    def test_command_workflow_and_permissions(self) -> None:
        self.run_cli("list")
        self.assertEqual(stat.S_IMODE((self.home / "auth.json").stat().st_mode), 0o600)
        self.assertEqual(
            stat.S_IMODE((self.home / "provider-profiles.json").stat().st_mode),
            0o600,
        )

        self.run_cli("save", "original")
        self.run_cli(
            "add",
            "proxy",
            "--base-url",
            "https://proxy.example/v1/",
            "--api-key-stdin",
            "--use",
            input_text="sk-test-proxy\n",
        )
        self.run_cli(
            "add",
            "duplicate",
            "--base-url",
            "https://proxy.example/v1",
            "--api-key",
            "sk-test-proxy",
            expected=2,
        )

        environment = dict(os.environ)
        environment["TEST_CODEX_PROFILE_KEY"] = "sk-test-edited"
        self.run_cli(
            "edit",
            "proxy",
            "--name",
            "proxy2",
            "--base-url",
            "https://edited.example/v1",
            "--api-key-env",
            "TEST_CODEX_PROFILE_KEY",
            env=environment,
        )

        config_text = (self.home / "config.toml").read_text()
        config = tomllib.loads(config_text)
        auth = json.loads((self.home / "auth.json").read_text())
        self.assertEqual(
            config["model_providers"]["OpenAI"]["base_url"],
            "https://edited.example/v1",
        )
        self.assertEqual(config["model"], "gpt-test")
        self.assertTrue(config["features"]["memories"])
        self.assertIn("# this comment must survive updates", config_text)
        self.assertEqual(auth["OPENAI_API_KEY"], "sk-test-edited")
        self.assertEqual(auth["other"], "preserved")

    def test_external_change_is_auto_saved_and_duplicates_are_merged(self) -> None:
        self.run_cli("list")
        registry_path = self.home / "provider-profiles.json"
        registry = self.load_registry()
        registry["profiles"]["copy"] = dict(registry["profiles"]["current"])
        registry["active"] = "copy"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        result = self.run_cli("list")
        self.assertIn("已自动去重", result.stdout)
        registry = self.load_registry()
        self.assertEqual(set(registry["profiles"]), {"current"})

        self.write_live("https://manual.example/v1", "sk-test-manual")
        result = self.run_cli("list")
        self.assertIn("已自动保存当前文件", result.stdout)
        registry = self.load_registry()
        self.assertEqual(len(registry["profiles"]), 2)
        active = registry["profiles"][registry["active"]]
        self.assertEqual(active["base_url"], "https://manual.example/v1")

    def test_full_interactive_menu_flow(self) -> None:
        menu_input = "\n".join(
            [
                "2",
                "proxy",
                "",
                "https://proxy.example/v1",
                "sk-test-proxy",
                "n",
                "",
                "3",
                "2",
                "proxy2",
                "",
                "https://edited.example/v1",
                "",
                "",
                "1",
                "2",
                "",
                "6",
                "",
                "1",
                "1",
                "",
                "4",
                "1",
                "y",
                "",
                "0",
                "",
            ]
        )
        result = self.run_cli(input_text=menu_input)
        self.assertIn("Codex 配置切换器", result.stdout)
        self.assertIn("已新增配置 'proxy'", result.stdout)
        self.assertIn("已修改配置 'proxy' -> 'proxy2'", result.stdout)
        self.assertIn("已切换到 'proxy2'", result.stdout)
        self.assertIn("已删除配置 'proxy2'", result.stdout)

        registry = self.load_registry()
        self.assertEqual(set(registry["profiles"]), {"current"})
        self.assertEqual(registry["active"], "current")
        auth = json.loads((self.home / "auth.json").read_text())
        self.assertEqual(auth["OPENAI_API_KEY"], "sk-test-original")

    def test_installer_uses_private_home_bin(self) -> None:
        install_home = self.home / "install-home"
        environment = dict(os.environ)
        environment["HOME"] = str(install_home)
        result = subprocess.run(
            [str(SCRIPT.parent / "install.sh")],
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        installed = install_home / ".local/bin/codex-profile"
        self.assertTrue(installed.is_file())
        self.assertEqual(stat.S_IMODE(installed.stat().st_mode), 0o755)
        version = subprocess.run(
            [str(installed), "--version"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(version.returncode, 0, msg=version.stderr)
        self.assertEqual(version.stdout.strip(), "codex-profile 1.1.0")


if __name__ == "__main__":
    unittest.main()
