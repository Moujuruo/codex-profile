#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="${1:-${script_dir}/codex-profile}"
install_dir="${HOME}/.local/bin"
install_file="${install_dir}/codex-profile"

python3 - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(
        "codex-profile requires Python 3.11 or newer; "
        f"found {sys.version_info.major}.{sys.version_info.minor}"
    )
PY

if [[ ! -f "${source_file}" ]]; then
    echo "error: cannot find ${source_file}" >&2
    exit 1
fi

mkdir -p "${install_dir}"
install -m 755 "${source_file}" "${install_file}"

echo "installed: ${install_file}"
if [[ ":${PATH}:" != *":${install_dir}:"* ]]; then
    echo "add this directory to PATH: ${install_dir}"
fi
echo "run: codex-profile"
