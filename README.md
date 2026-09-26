# codex-profile

一个无 Web UI、无第三方依赖的 Codex 配置切换器，用于保存和切换
`config.toml` 中的 `base_url`、`wire_api` 与 `auth.json` 中的 API key。

直接运行 `codex-profile` 会进入中文交互菜单；原子命令仍可用于脚本和自动化。

## 功能

- 首次运行自动保存当前 Codex 配置
- 交互式新增、切换、修改、重命名和删除配置
- 每组配置记录 `wire_api`（`responses` 或 `chat`），切换时同步写入 `config.toml`
- 按 `provider + base_url + wire_api + API key` 自动去重
- 检测并自动保存外部手工修改
- 切换前自动备份 `config.toml` 和 `auth.json`
- 原子写入，失败时尝试回滚
- API key 隐藏输入，列表只显示短 SHA-256 标识
- 配置库、凭据和备份使用私有文件权限

## 运行要求

- Linux 或 macOS
- Python 3.11 或更高版本
- 已存在 `~/.codex/config.toml`
- 已存在文件式凭据 `~/.codex/auth.json`
- `config.toml` 使用自定义 `model_provider`，并在对应的
  `[model_providers.<id>]` 表中包含 `base_url`

Windows 用户可以在 WSL 中运行。当前版本依赖 Unix 的 `fcntl` 文件锁，不能直接
运行在原生 Windows Python 中。

## 安装

### 从 GitHub Release 安装

下载已发布的固定版本和校验和（`v1.1.0`；本文所述 `wire_api` 功能需从源码安装，等待后续 Release）：

```bash
version=v1.1.0
release="https://github.com/Moujuruo/codex-profile/releases/download/${version}"
install_dir="$(mktemp -d)"

curl -fL "${release}/codex-profile" -o "${install_dir}/codex-profile"
curl -fL "${release}/SHA256SUMS" -o "${install_dir}/SHA256SUMS"

cd "${install_dir}"
sha256sum -c SHA256SUMS
install -Dm755 codex-profile "${HOME}/.local/bin/codex-profile"
```

macOS 校验命令：

```bash
shasum -a 256 -c SHA256SUMS
mkdir -p "${HOME}/.local/bin"
install -m 755 codex-profile "${HOME}/.local/bin/codex-profile"
```

如果 `~/.local/bin` 不在 `PATH`，将下面一行加入 shell 配置：

```bash
export PATH="${HOME}/.local/bin:${PATH}"
```

### 从源码安装

```bash
git clone https://github.com/Moujuruo/codex-profile.git
cd codex-profile
./install.sh
```

安装脚本只复制程序并检查 Python 版本，不会读取或修改 Codex 凭据。

## 使用

启动交互菜单：

```bash
codex-profile
```

菜单提供以下操作：

```text
1. 切换配置
2. 新增配置
3. 修改配置
4. 删除配置
5. 保存或重命名当前配置
6. 查看全部配置
7. 立即备份
0. 退出
```

常用原子命令：

```bash
codex-profile list
codex-profile current
eval "$(codex-profile env)"  # 让 OpenAI SDK/imagegen CLI 使用当前配置
codex-profile save original
codex-profile add proxy --base-url https://api.example.com/v1
codex-profile add chat-proxy --base-url https://chat.example.com/v1 --wire-api chat
codex-profile use proxy
codex-profile edit proxy
codex-profile delete proxy
codex-profile backup
```

每组配置都会记录 `wire_api`：`responses`（默认值，对应 Responses API）或
`chat`（对应 Chat Completions API）。切换配置时会把它写入当前 provider 的
`[model_providers.<id>]` 表；表中缺少该字段时会自动补上。旧版本保存的配置
没有此字段，加载时按 `responses` 处理，可用 `codex-profile edit <名称>
--wire-api chat` 修改。新增配置不传 `--wire-api` 时沿用当前值。

注意：当前版本的 Codex 已移除对 `wire_api = "chat"` 的支持，配置后启动会直接
报错（见 [openai/codex#7782](https://github.com/openai/codex/discussions/7782)）。
`chat` 仅对旧版本 Codex 有意义，使用 chat 配置时程序会向 stderr 打印警告。

`codex-profile` 直接修改 Codex 的 `config.toml` 和 `auth.json`。其他使用 OpenAI
SDK 的工具通常读取环境变量；可用 `eval "$(codex-profile env)"` 将当前活动配置
导出到当前 shell。该命令会输出用于 `eval` 的 key 环境变量，请只交给受信任的
shell，避免在共享终端中执行或记录输出。

新增时不传 `--api-key` 会进入隐藏输入。自动化场景建议通过环境变量或标准输入
传递密钥，避免进入 shell 历史：

```bash
codex-profile add proxy \
  --base-url https://api.example.com/v1 \
  --api-key-env OPENAI_API_KEY \
  --use
```

完整帮助：

```bash
codex-profile --help
codex-profile add --help
```

如果使用了自定义 `CODEX_HOME`：

```bash
CODEX_HOME=/path/to/codex-home codex-profile
```

也可以使用全局选项：

```bash
codex-profile --codex-home /path/to/codex-home list
```

## 数据与安全

程序会在 `CODEX_HOME`（默认 `~/.codex`）中创建：

```text
provider-profiles.json
provider-profile-backups/
.provider-profiles.json.lock
```

同一 `CODEX_HOME` 同时只能运行一个实例。交互菜单尚未退出时，另一个实例会立即
提示占用情况；回到先启动的菜单输入 `0` 退出后即可继续。

为了完成离线切换，`provider-profiles.json` 和备份中的 `auth.json` 包含明文
API key。程序将敏感文件设为 `0600`、备份目录设为 `0700`，但这些文件仍应按
密码文件处理：

- 不要提交到 Git
- 不要发送给其他人
- 不要粘贴到 issue、工单或聊天中
- 不要用 root 运行，除非确实要管理 `/root/.codex`

仓库中的 `.gitignore` 会忽略常见 Codex 凭据文件，但它不能替代发布前的人工检查。

## 开发与测试

测试只使用临时目录和虚假密钥，不接触真实 `~/.codex`：

```bash
python3 -m unittest discover -s tests -v
```

生成发布校验和：

```bash
sha256sum codex-profile > SHA256SUMS
```

## 许可证

[MIT](LICENSE)
