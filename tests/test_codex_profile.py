from __future__ import annotations

import json
import os
import fcntl
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
            timeout=5,
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

    def test_env_exports_active_profile_for_openai_sdk(self) -> None:
        self.run_cli("save", "original")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--codex-home", str(self.home), "env"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("export OPENAI_BASE_URL=https://original.example/v1", result.stdout)
        self.assertIn("export OPENAI_API_KEY=sk-test-original", result.stdout)

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
                "",
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

    def test_wire_api_switching(self) -> None:
        self.run_cli("save", "original")
        result = self.run_cli(
            "add",
            "chatproxy",
            "--base-url",
            "https://chat.example/v1",
            "--wire-api",
            "chat",
            "--api-key-stdin",
            "--use",
            input_text="sk-test-proxy\n",
        )
        self.assertIn('wire_api = "chat"', result.stderr)
        config = tomllib.loads((self.home / "config.toml").read_text())
        provider = config["model_providers"]["OpenAI"]
        self.assertEqual(provider["base_url"], "https://chat.example/v1")
        self.assertEqual(provider["wire_api"], "chat")

        result = self.run_cli("use", "original")
        self.assertIn("wire_api: responses", result.stdout)
        config = tomllib.loads((self.home / "config.toml").read_text())
        provider = config["model_providers"]["OpenAI"]
        self.assertEqual(provider["base_url"], "https://original.example/v1")
        self.assertEqual(provider["wire_api"], "responses")

        result = self.run_cli("current")
        self.assertIn("wire_api: responses", result.stdout)
        result = self.run_cli("list")
        self.assertIn("chat", result.stdout)

    def test_wire_api_inserted_when_missing(self) -> None:
        (self.home / "config.toml").write_text(
            CONFIG_TEMPLATE.replace('wire_api = "responses"\n', "").format(
                base_url="https://original.example/v1"
            ),
            encoding="utf-8",
        )
        self.run_cli("save", "original")
        self.run_cli(
            "add",
            "chatproxy",
            "--base-url",
            "https://chat.example/v1",
            "--wire-api",
            "chat",
            "--api-key-stdin",
            "--use",
            input_text="sk-test-proxy\n",
        )
        config = tomllib.loads((self.home / "config.toml").read_text())
        self.assertEqual(config["model_providers"]["OpenAI"]["wire_api"], "chat")

        self.run_cli("use", "original")
        config = tomllib.loads((self.home / "config.toml").read_text())
        self.assertEqual(config["model_providers"]["OpenAI"]["wire_api"], "responses")
        registry = self.load_registry()
        self.assertEqual(registry["profiles"]["original"]["wire_api"], "responses")

    def test_wire_api_inserted_at_eof_without_final_newline(self) -> None:
        config_path = self.home / "config.toml"
        config_path.write_text(
            'model_provider = "OpenAI"\n'
            '[model_providers.OpenAI]\n'
            'base_url = "https://original.example/v1"',
            encoding="utf-8",
        )
        self.run_cli("save", "original")
        self.run_cli(
            "add", "chatproxy",
            "--base-url", "https://chat.example/v1",
            "--wire-api", "chat",
            "--api-key-stdin", "--use",
            input_text="sk-test-proxy\n",
        )
        config = tomllib.loads(config_path.read_text())
        provider = config["model_providers"]["OpenAI"]
        self.assertEqual(provider["base_url"], "https://chat.example/v1")
        self.assertEqual(provider["wire_api"], "chat")
        self.run_cli("use", "original")
        config = tomllib.loads(config_path.read_text())
        self.assertEqual(
            config["model_providers"]["OpenAI"]["wire_api"], "responses"
        )

    def test_registry_profiles_without_wire_api_default_to_responses(self) -> None:
        self.run_cli("save", "original")
        registry_path = self.home / "provider-profiles.json"
        registry = self.load_registry()
        for profile in registry["profiles"].values():
            profile.pop("wire_api", None)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        self.run_cli("list")
        registry = self.load_registry()
        self.assertTrue(registry["profiles"])
        for profile in registry["profiles"].values():
            self.assertEqual(profile["wire_api"], "responses")

    def test_invalid_wire_api_is_rejected(self) -> None:
        result = self.run_cli(
            "add",
            "bad",
            "--base-url",
            "https://bad.example/v1",
            "--wire-api",
            "bogus",
            "--api-key-stdin",
            input_text="sk-test-proxy\n",
            expected=2,
        )
        self.assertIn("wire-api", result.stderr)

    def test_busy_lock_returns_actionable_error_without_waiting(self) -> None:
        lock_path = self.home / ".provider-profiles.json.lock"
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            result = self.run_cli("list", expected=2)

        self.assertIn("另一个 codex-profile 实例正在使用配置", result.stderr)
        self.assertIn("输入 0 退出后再试", result.stderr)

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
        self.assertEqual(version.stdout.strip(), "codex-profile 1.2.0")


if __name__ == "__main__":
    unittest.main()
