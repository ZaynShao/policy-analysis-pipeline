# Runbook: 微信读书 QR 按需重发(openclaw MCP 工具)

**目的**：token 失效推码后,若主人没赶上扫码窗口而二维码过期,可对 OPC(openclaw agent,Feishu)说"重发码/码过期了"按需重新推送,无需等下一个 09:30 哨兵 cron。

## 组成(全部已在 main)

| 件 | 路径 | 作用 |
|---|---|---|
| 纯逻辑 | `scripts/l1_collect/commentary_ingest/qr_relay/resend.py` | 查 token:有效→noop;失效→后台 detached 拉起现有 `qr_relay.run`(推码+轮询300s+落库+回执) |
| MCP server | `scripts/l1_collect/commentary_ingest/qr_relay/mcp_server.py` | FastMCP stdio,暴露单工具 `resend_wewe_qr`,读 env `WEWE_DB_PATH` |
| 启动器 | `scripts/l1_collect/commentary_ingest/qr_relay/wewe-qr-mcp.sh` | source env 文件 + 设 `WEWE_QR_DIR` + exec mcp_server(凭据不进 openclaw.json) |
| 渲染 | `qr_render.py` | QR 渲染为 **RGB** PNG(1-bit 灰度会被 Feishu 退化成文件附件,2026-06-12 修) |

## 服务器接线步骤(在 VPS 8.216.59.173,可重复)

```bash
# 1. 依赖:哨兵 venv 装 MCP SDK
/root/policy-sentinel-venv/bin/pip install mcp

# 2. 部署代码(随 main)
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main
chmod +x scripts/l1_collect/commentary_ingest/qr_relay/wewe-qr-mcp.sh

# 3. 注册 MCP server(command 指向 repo checkout 内的启动器,单一来源随 git 更新)
openclaw mcp set wewe-qr-relay \
  '{"command":"/root/policy-pipeline-src/scripts/l1_collect/commentary_ingest/qr_relay/wewe-qr-mcp.sh","args":[]}'

# 4. 让 agent 重建工具表(新增 MCP server 必须重启网关;仅改 server 内部代码用 reload 即可)
XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart openclaw-gateway   # 首次注册
# openclaw mcp reload                                                     # 后续仅代码更新

# 5. 验证(不推码)
openclaw mcp probe wewe-qr-relay     # 期望: 1 tools (resend_wewe_qr)
```

## OPC 识别(消歧)——openclaw workspace AGENTS.md

openclaw 的设备配对/WhatsApp/Telegram 链接也用二维码,会与本工具竞争语义。必须在**注入系统提示的** `AGENTS.md`(`/root/.openclaw/workspace/AGENTS.md`,注意 **不是** TOOLS.md——后者不注入)写消歧规则:

> 本节点部署了政策 pipeline 的微信读书(wewe-rss)采集。主人提到"微信读书/RSS 的 二维码/码/扫码 失效/过期/扫不上/重发"时,**立即调用 `wewe-qr-relay__resend_wewe_qr`**(无参);不要与 openclaw 设备配对码混淆,不要反问是哪种码。

(权威工具名 `wewe-qr-relay__resend_wewe_qr`,`prompts_*`/`resources_*` 是 MCP 脚手架非工具。)

## 已知约束 / 待硬化

- **网关重启会杀在途 relay**:relay 跑在网关 systemd cgroup 内,`start_new_session` 只换会话不换 cgroup,`systemctl restart` 整组杀。改配置须避开扫码窗口。根治:relay 改用 `systemd-run --scope` 脱离网关 cgroup(未做)。
- `mcp reload` 不杀在途 relay(仅 dispose 缓存运行时),改 server 代码优先用 reload。

## 历史

- 2026-06-12 接线 + RGB 渲染修复;OPC 识别经重启网关 + AGENTS.md 消歧后端到端跑通(主人扫码 token 恢复)。
