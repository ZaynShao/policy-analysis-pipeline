# OpenClaw QR Relay Build Report

Date: 2026-06-08 00:56 +0800
Branch: `codex/openclaw-qr-relay`
Workspace: `/Users/shaoziyuan/dev/政策分析-pipeline`

## Purpose

Implement and validate the module for:

`wewe-rss 微信读书 token 失效 -> 自动生成重新登录二维码 -> 通过 OpenClaw 推送到 IM -> 用户扫码 -> 轮询确认 -> 发恢复/失败通知`

The working IM for this drill is Feishu through local OpenClaw. WeChat was tested first, but proactive QR image delivery was not stable enough; Feishu text and image delivery were verified end to end.

## Current Status

- Code branch exists: `codex/openclaw-qr-relay`.
- Module implemented under `scripts/l1_collect/commentary_ingest/qr_relay/`.
- Tests implemented under `tests/commentary_qr_relay/`.
- Multi-account SQLite fallback now treats "at least one account status=1" as healthy.
- Daily local launchd verification is configured.
- Feishu OpenClaw channel is configured locally and paired.
- Real Feishu text delivery confirmed by user for markers `001`, `002`, and `006`.
- Real Feishu QR/image delivery confirmed by user through marker `005`.
- Real wewe-rss login QR was generated and sent to Feishu during drill.
- User scanned the QR.
- After scan, real feed endpoints returned HTTP 200:
  - `/feeds/all.atom`
  - `/feeds/all.rss`
  - `/feeds/all.json`
- Local wewe-rss DB status restored to `1` after the drill.

## Added Files

Implementation:

- `scripts/l1_collect/commentary_ingest/__init__.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/__init__.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/detector.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/wewe_login.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/feed_health.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/qr_render.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/openclaw.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/run.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/daily_check.py`
- `scripts/l1_collect/commentary_ingest/qr_relay/requirements.txt`

Tests:

- `tests/commentary_qr_relay/test_detector.py`
- `tests/commentary_qr_relay/test_wewe_login.py`
- `tests/commentary_qr_relay/test_feed_health.py`
- `tests/commentary_qr_relay/test_qr_render.py`
- `tests/commentary_qr_relay/test_openclaw.py`
- `tests/commentary_qr_relay/test_run.py`
- `tests/commentary_qr_relay/test_daily_check.py`

Reports:

- `docs/handoffs/2026-06-08-openclaw-qr-relay-build-report.md`
- `docs/handoffs/2026-06-08-openclaw-qr-relay-build-report.html`

## Architecture

### Detection

File: `detector.py`

- Public seam: `token_needs_relay(db_path) -> TokenStatus`.
- It lazily imports `scripts.l1_collect.commentary_ingest.token_health` if available.
- If that module is absent in this branch, it falls back to reading SQLite `accounts.status`.
- Fallback rule:
  - no DB or unreadable DB -> invalid
  - empty `accounts` -> invalid
  - any `status == 1` -> valid
  - no `status == 1` -> invalid

This preserves the intended seam while keeping the current branch additive.

### Daily Feed Health

Files: `feed_health.py`, `daily_check.py`

- `feed_health.py` performs a real `/feeds/all.atom` HTTP check with `Authorization: Bearer <AUTH_CODE>`.
- `daily_check.py` uses that real feed health result as the daily detector.
- If feed health is valid, it exits without sending IM.
- If feed health fails, it enters the QR relay flow and then confirms recovery with the same real feed detector.

### wewe-rss Login

File: `wewe_login.py`

Implements the tRPC flow from the handoff spec:

- `POST /trpc/platform.createLoginUrl`
  - headers: bare `Authorization: <AUTH_CODE>`
  - body: `{}`
  - response shape: `{"result":{"data":{"uuid": "...", "scanUrl": "..."}}}`
- `GET /trpc/platform.getLoginResult?input=<urlencoded {"id":"<uuid>"}>`
  - headers: bare `Authorization: <AUTH_CODE>`
  - response shape: `{"result":{"data": ...}}`

Polling behavior:

- timeouts are treated as pending
- HTTP request errors are treated as pending until timeout
- successful shapes include explicit statuses such as `confirmed`, `success`, `logged_in`, `login_success`, or payloads containing `token`, `user`, `account`, `ok=true`, or `success=true`

### QR Rendering

File: `qr_render.py`

- Pure function: scan URL text -> PNG path.
- Uses `qrcode` if available, `segno` fallback if installed.
- Dependency declared in `requirements.txt`: `qrcode[pil]>=7.4`.

### OpenClaw Adapter

File: `openclaw.py`

Interface shape:

- `push_qr(image_path, caption, target) -> bool`
- `push_text(message, target) -> bool`

Implemented adapters:

- `OpenClawMessageAdapter`
  - uses `openclaw message send`
  - supports channel/account/target via env or CLI config
  - used successfully with Feishu
- `DiscordBotAdapter`
  - preserved as a direct Discord Bot API adapter from the earlier Discord path
- `OpenClawNotifyFallback`
  - text-only fallback through `oc-ctl notify`

### Orchestration

File: `run.py`

Main flow:

1. Check token.
2. If token is valid, exit successfully without sending QR.
3. If token is invalid, call `createLoginUrl`.
4. Render QR PNG.
5. Push QR to IM.
6. Poll `getLoginResult(uuid)` until success or timeout.
7. Confirm token restored with repeated detector checks.
8. Send final IM text:
   - restored: `微信读书扫码已确认,wewe-rss token 已恢复。`
   - not restored: `微信读书扫码已确认,但 token 健康检查仍未恢复。`
   - timeout: `微信读书扫码超时,wewe-rss token 未恢复。`
9. If QR push fails or timeout happens, fall back to existing alert seam where available, then `oc-ctl notify`.

Environment/CLI inputs:

- `WEWE_DB_PATH` or `--db-path`
- `WEWE_QR_DIR` or `--qr-dir`
- `WEWE_BASE_URL` or `--wewe-base-url`
- `WEWE_AUTH_CODE` or `--auth-code`
- `OPENCLAW_CHANNEL` / `OPENCLAW_IM_CHANNEL`
- `OPENCLAW_ACCOUNT`
- `OPENCLAW_IM_TARGET` or `--target`
- `OPENCLAW_COMMAND`
- `ALERT_WEBHOOK_URL`
- `WEWE_LOGIN_TIMEOUT`
- `WEWE_LOGIN_INTERVAL`

## Feishu/OpenClaw Build Notes

Local OpenClaw:

- Upgraded OpenClaw core to `2026.6.1 (2e08f0f)`.
- Installed `@openclaw/feishu@2026.6.1`.
- Configured Feishu channel:
  - `channels.feishu.enabled=true`
  - `channels.feishu.defaultAccount=main`
  - `channels.feishu.accounts.main.name=policy-qr-relay`
  - `channels.feishu.connectionMode=websocket`
  - `channels.feishu.domain=feishu`
- Gateway reported Feishu channel `running=true`, `lastError=null`.
- Feishu WebSocket became ready.

Feishu developer-side requirement observed from plugin logs:

- Developer Console -> Events and Callbacks -> subscription mode must be "receive events/callbacks through persistent connection".
- Required event observed in plugin source: `im.message.receive_v1`.

Pairing:

- User sent a message to the Feishu bot.
- OpenClaw received inbound event from a Feishu sender and generated pairing code.
- Pairing was approved.
- `commands.ownerAllowFrom` was configured for the Feishu sender.

Verified delivery:

- `openclaw message send --channel feishu --account main --target <feishu-open-id> --message ...`
- `openclaw message send --channel feishu --account main --target <feishu-open-id> --message ... --media <png>`

Both text and image were confirmed by the user.

## Drill Evidence

### Feishu IM

User confirmed:

- text marker `001` received
- text marker `002` received
- QR/image marker through `005` received

### Real QR Relay Drill

Drill action:

- Backed up current DB account status.
- Temporarily set `accounts.status=0` in local `~/wewe-rss-data/wewe-rss.db` to trigger the invalid-token branch.
- Ran `relay_once` with:
  - `OPENCLAW_CHANNEL=feishu`
  - `OPENCLAW_ACCOUNT=main`
  - target = paired Feishu sender open id
  - wewe-rss base URL = `http://localhost:4000`
- QR generated at:
  - `/tmp/wewe_qr_relay_feishu_drill/wewe-login-071D2fLs3ec2ll2J.png`
- User scanned the QR.
- DB status was restored to `1` in `finally`.

Important nuance:

Because the drill forced `accounts.status=0` for triggering, the orchestration's final fallback detector saw the artificial DB invalid state before the script restored it. That produced a "scan confirmed but health check still invalid" result in the script output. This was a drill artifact, not a real token failure.

Post-drill real health check:

- DB account status: `1`
- `/feeds/all.atom`: HTTP 200
- `/feeds/all.rss`: HTTP 200
- `/feeds/all.json`: HTTP 200

This is the effective closure proof: QR scan completed and real feed access is currently valid.

## Tests

Command:

```bash
python3 -m pytest tests/commentary_qr_relay -q
```

Result:

```text
18 passed, 1 warning
```

Compile check:

```bash
python3 -m compileall -q scripts/l1_collect/commentary_ingest tests/commentary_qr_relay
```

Result: passed.

Credential scan:

```bash
rg -n '<known-app-ids>|<known-app-secrets>|<server-password>|<jwt-prefix>' scripts/l1_collect/commentary_ingest tests/commentary_qr_relay docs/handoffs
```

Result: no matches.

## Known Limits / Follow-Up

1. Wire into the actual production trigger:
   - `token_health.check_token`
   - `run.py --check-token` or the existing token health scheduler path

2. Avoid DB-forced false negatives in future drills:
   - for realistic recovery drills, use the real token health seam instead of manually holding `accounts.status=0`
   - or make drill mode restore DB before the final detector confirmation

3. Configure production env outside git:
   - `WEWE_DB_PATH`
   - `WEWE_AUTH_CODE`
   - `OPENCLAW_CHANNEL=feishu`
   - `OPENCLAW_ACCOUNT=main`
   - `OPENCLAW_IM_TARGET=<paired target>`

4. Keep deployment on a domestic node or local domestic network:
   - token belongs to a personal WeChat Reading account
   - Tokyo IP was explicitly rejected as risky due to WeChat geo-risk

5. WeChat OpenClaw channel remains non-primary:
   - text eventually worked
   - image delivery was inconsistent
   - Feishu is the tested channel for this branch

## Local Daily Verification

Configured after the Feishu drill:

- LaunchAgent:
  - `~/Library/LaunchAgents/com.zayn.policy.wewe-qr-relay-daily.plist`
- Local env file:
  - `~/.config/policy-pipeline/wewe-qr-relay.env`
- Wrapper:
  - `~/.local/bin/policy-wewe-qr-relay-daily`
- Logs:
  - `~/Library/Logs/policy-pipeline/wewe-qr-relay-daily.log`
  - `~/Library/Logs/policy-pipeline/wewe-qr-relay-daily.err`
- Schedule:
  - every day at 09:30 local time

Credential behavior:

- real `AUTH_CODE` is not stored in the env file
- the wrapper reads `AUTH_CODE` dynamically from the running `wewe-rss` container
- Feishu app secret remains in local OpenClaw config, not in this repo

Manual verification:

```bash
~/.local/bin/policy-wewe-qr-relay-daily
```

Observed result:

```json
{"checked": true, "relayed": false, "restored": true, "detail": "feed health ok: /feeds/all.atom HTTP 200", "qr_path": ""}
```

launchd verification:

```bash
launchctl kickstart -k gui/$(id -u)/com.zayn.policy.wewe-qr-relay-daily
launchctl print gui/$(id -u)/com.zayn.policy.wewe-qr-relay-daily
```

Observed status:

- `runs = 1`
- `last exit code = 0`

## Suggested Production Command Shape

Do not put real credentials in git. Use a local env file or service secret manager.

```bash
OPENCLAW_CHANNEL=feishu \
OPENCLAW_ACCOUNT=main \
OPENCLAW_IM_TARGET='<paired-feishu-target>' \
WEWE_DB_PATH="$HOME/wewe-rss-data/wewe-rss.db" \
WEWE_BASE_URL='http://localhost:4000' \
WEWE_AUTH_CODE='<secret>' \
python3 -m scripts.l1_collect.commentary_ingest.qr_relay.run
```

## Merge Readiness

Ready to merge into the main session as an additive feature branch, with one caveat:

- the production hook into the existing token health scheduler/CLI should be done in the main session because this branch intentionally avoided editing existing files.

No known credentials were committed or written into the new module/test files.
