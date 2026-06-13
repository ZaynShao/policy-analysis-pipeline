# Codex 交接：QR 按需重发 MCP 工具（本地代码侧）

**背景**：微信读书 token 失效时哨兵推二维码（`qr_relay/run.py`）。若码过期，用户对 OPC（openclaw agent）说"码过期了"，OPC 无任何把手重发。本包给 OPC 一个 MCP 工具 `resend_wewe_qr`：查 token → 有效则报"仍有效"／失效则后台拉起现有 relay（推新码+轮询+落库+回执，**全部复用 run.py，零改动核心逻辑**）秒返回"已重发"。

**关键事实（读 `scripts/l1_collect/commentary_ingest/qr_relay/run.py` 确认）**：
- 检测函数：`from .detector import token_needs_relay`；`token_needs_relay(Path(db_path)) -> TokenStatus`，字段 `valid: bool / detail: str / account_name`。
- 完整 relay 入口：`python -m scripts.l1_collect.commentary_ingest.qr_relay.run`（`config_from_env` 吃 env：`WEWE_DB_PATH / WEWE_QR_DIR / OPENCLAW_IM_TARGET / WEWE_BASE_URL / WEWE_AUTH_CODE / OPENCLAW_CHANNEL(或 OPENCLAW_IM_CHANNEL) / OPENCLAW_ACCOUNT / OPENCLAW_COMMAND`）。它内部已含：token 有效短路、推码、轮询 300s、扫码落库、**成功/超时/失败各自回执**（run.py:80,97,99）——**不要重写这些**。
- 服务器 relay 运行 env 来自 `/etc/policy-pipeline/notify.env` + `/etc/policy-pipeline/commentary.env`（与 09:30 哨兵 cron 同源）。

**纪律（红线）**：TDD 红绿分 commit；只许新建 `qr_relay/resend.py` + `qr_relay/mcp_server.py` + `tests/commentary_qr_relay/test_resend.py` + 改 `qr_relay/run.py` 的 caption 一行 + `qr_relay/requirements.txt` 加 `mcp`；既有未跟踪文件不碰；不合 main 不 push；不碰 vault；凭据值盲（脚本不得硬编码任何 token/auth_code，全走 env）。

**分支**：`qr/resend-mcp`（从 main 最新起）。

## 改动 1 · `qr_relay/resend.py`（纯逻辑，可单测）

```python
def resend_wewe_qr(db_path, *, detector=token_needs_relay, spawn=None) -> dict:
    """查 token;有效→不重发;失效→后台拉起 relay。返回结构化 dict。"""
```
- 同步调 `detector(Path(db_path))`；
- `status.valid` → 返回 `{"action": "noop", "valid": True, "message": "token 仍有效,无需重发"}`，**不 spawn**；
- 失效 → 调 `spawn`（默认实现=`subprocess.Popen` 启动 `[sys.executable, "-m", "scripts.l1_collect.commentary_ingest.qr_relay.run"]`，**detached**：`start_new_session=True` + stdout/stderr 重定向到 `/var/log/policy-pipeline/qr_relay.log`(或 env `QR_RELAY_LOG`，缺省走 DEVNULL)，**不 wait**），返回 `{"action": "resent", "valid": False, "message": "已重新推送二维码,请扫描;扫码成功会收到确认"}`；
- spawn 注入 env=当前 `os.environ`（live 由 MCP 进程继承，见注册侧）。
- 默认 spawn 抽成可注入参数,测试用 mock spawn 计数(valid→spawn 调 0 次;invalid→1 次)+断言返回 dict。

## 改动 2 · `qr_relay/mcp_server.py`（薄 MCP 封装,不强求单测）

用官方 `mcp` SDK（`from mcp.server.fastmcp import FastMCP` 或等价低层 API,以装上的版本为准）起一个 stdio server,注册单个工具：

```
tool: resend_wewe_qr()  描述(给 LLM 看,务必明确触发场景):
  "当用户提到微信/读书/RSS 的二维码/码/扫码 过期、失效、扫不上、没反应、要求重发/再发一张 时调用。
   会检查登录态:仍有效则告知无需重发;已失效则立即重新推送一张新二维码。"
```
工具体内 `db_path` 取 env `WEWE_DB_PATH`,调 `resend.resend_wewe_qr(db_path)`,把返回 dict 的 `message` 作为工具结果文本返回。`if __name__=="__main__": mcp.run()`(stdio)。

## 改动 3 · `run.py` caption 暗号（一行）

`run.py:67` 附近,推码 caption 末尾补固定暗号,使自然语识别有兜底锚点：
```python
    caption = caption + "\n(过期/扫不上 → 回我『重发码』即可重新推送)"
    caption = caption + (f"\n{config.note}" if config.note else "")
```
（顺序:暗号在 note 之前或之后均可,保证两者都在。）

## 改动 4 · `requirements.txt` 加 `mcp`

`qr_relay/requirements.txt` 追加 `mcp`(MCP Python SDK)。

## 验证

`python3 -m pytest tests/commentary_qr_relay/ -q` 全绿（含新 test_resend + 既有 daily_check 测试不破）；`python3 -c "import ast; ast.parse(open('scripts/l1_collect/commentary_ingest/qr_relay/mcp_server.py').read())"` 语法过（mcp 未装时 import 会失败,故 mcp_server 不进 pytest 收集——放 import 守卫或确保测试不 import 它）。

## 回报

stdout：分支、红绿 commit、pytest 数字、mcp_server 采用的 SDK API 形式、resend 默认 spawn 的确切命令行。无需 report 文件。
