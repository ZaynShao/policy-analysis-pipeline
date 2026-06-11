# WP-3b 服务器部署监督报告

时间: 2026-06-11 16:30 CST

结论: **中止于 Step 1 manifest 初始化**。`origin/main` 的 `c638cef` checkout 中缺少交接要求的 `state/source_ready/market_intel_manifest.jsonl`, 因此未进入 Step 2 首跑、Step 3 投影、Step 4 cron、Step 5 哨兵实测。

## Step 0 部署

命令:

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
git rev-parse --short HEAD
docker run --rm policy-pipeline:latest python -c "import scripts.commentary_signals.run, scripts.market_intel_signals.run, scripts.derived_signals.run; print('IMAGE_OK')"
```

关键输出:

```text
HEAD is now at c638cef fix(signals): wire nightly signal health checks
c638cef
IMAGE_OK
```

结果: 通过。未重建镜像。

## Step 1 manifest 初始化

命令:

```bash
mkdir -p /root/policy-pipeline-state/source_ready
test -f /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl && echo "已存在,跳过" || \
  cp /root/policy-pipeline-src/state/source_ready/market_intel_manifest.jsonl /root/policy-pipeline-state/source_ready/
wc -l /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl
```

关键输出:

```text
cp: cannot stat '/root/policy-pipeline-src/state/source_ready/market_intel_manifest.jsonl': No such file or directory
```

只读诊断:

```bash
cd /root/policy-pipeline-src
git ls-tree -r --name-only HEAD | grep -E '(^|/)market_intel_manifest\.jsonl$|source_ready' || true
find state -maxdepth 4 -type f | sort | sed -n '1,120p'
```

关键结论:

```text
git ls-tree 未找到 market_intel_manifest.jsonl 或 source_ready 路径。
find state ... 输出中未出现 state/source_ready/market_intel_manifest.jsonl。
```

结果: 未通过。期望行数 23 无法验证。

## Step 2 监督首跑

未执行。原因: Step 1 manifest 缺失, 按红线停止。

未产生 commentary dry-run / market dry-run / derived preview 数字。未执行 `derived_signals apply`, 未执行 `produce_and_push`, 未写 vault。

## Step 3 投影验证

未执行。原因: Step 1 未通过, Step 2 未完成。

未产生 `commentary_count` / `relation_count`。

## Step 4 安装 03:00 cron

未执行。原因: 信号链首跑未通过前不接 cron。

## Step 5 哨兵新口径实测

未执行。原因: 前置部署链已中止。

## 当前状态与建议

- 服务器 `/root/policy-pipeline-src` 已更新到 `c638cef`。
- 现有 Docker 镜像 import 闸通过, 但未重建镜像。
- `/root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl` 未初始化。
- 未执行任何信号链 apply / produce_and_push, 未安装 03:00 cron, 未触发 QR relay。

推荐下一步: 先补齐或确认 `market_intel_manifest.jsonl` 的来源并合入/分发到服务器可用路径, 再从 Step 1 重新开始。不要跳过 Step 1 直接跑 Step 2, 因为 market dry-run 的 Done Gate 依赖该 manifest。

## 续跑

时间: 2026-06-11 16:34-16:40 CST

结论: **完成 Step 0→5**。服务器 checkout 更新到 `42608af`, manifest 初始化通过, 信号链监督首跑完成并 push vault, 投影 `errors=[]`, 03:00 cron 已安装, QR relay 哨兵实测为 token 有效的 no-op。

### Step 0 部署

命令:

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
git rev-parse --short HEAD
docker run --rm policy-pipeline:latest python -c "import scripts.commentary_signals.run, scripts.market_intel_signals.run, scripts.derived_signals.run; print('IMAGE_OK')"
```

关键输出:

```text
HEAD is now at 42608af data(source-ready): track market_intel manifest seed (23 reviewed rows) for server distribution
42608af
IMAGE_OK
```

结果: 通过。未重建镜像。

### Step 1 manifest 初始化

命令:

```bash
mkdir -p /root/policy-pipeline-state/source_ready
test -f /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl && echo "已存在,跳过" || \
  cp /root/policy-pipeline-src/state/source_ready/market_intel_manifest.jsonl /root/policy-pipeline-state/source_ready/
wc -l /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl
git -C /root/policy-pipeline-src ls-files state/source_ready/market_intel_manifest.jsonl
```

关键输出:

```text
23 /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl
state/source_ready/market_intel_manifest.jsonl
```

结果: 通过。

### Step 2 监督首跑

按 03:00 信号链四段在 `/var/lock/policy-pipeline-producer.lock` 下顺序执行。手跑时因 `ssh ... bash -s` 会被 `docker compose run` 消耗 stdin, 改为远端临时脚本执行;前两次仅重复 commentary dry-run,未进入 apply,未写 vault。最终监督跑完整通过。

commentary dry-run:

```text
COMMENTARY_SUMMARY {"total_commentaries": 405, "linked_commentaries": 211, "emitted_signals": 211, "review_queue": 25, "skipped_unlinked": 142, "skipped_not_policy_related": 52}
```

market dry-run:

```text
MARKET_SUMMARY {"manifest_rows": 23, "located_raw": 19, "emitted_signals": 19, "review_queue": 18, "by_queue_reason": {"manifest_pid_not_found": 4, "theme_not_found": 11, "region_unknown": 3}}
```

判定: 通过 signal-or-queue 门。19 行 manifest 产出 signal, 4 行进入 `manifest_pid_not_found` queue;无 manifest 行静默丢失。

derived preview:

```text
DERIVED_PREVIEW_SUMMARY {"candidate_commentary_signals": 211, "candidate_market_intel_signals": 19, "commentary_signals": 186, "market_intel_signals": 6, "blocked_signals": 38, "blocked_commentary_signals": 25, "blocked_market_intel_signals": 13}
```

derived apply:

```text
DERIVED_APPLY_SUMMARY {"written": ["1_extracted/commentary_signals.jsonl", "1_extracted/market_intel_signals.jsonl"], "commentary_signals": 186, "market_intel_signals": 6, "raw_writes": 0, "source_preview_state": "/state/derived_signals/nightly"}
```

apply 后 vault 白名单门:

```text
 M 1_extracted/commentary_signals.jsonl
 M 1_extracted/market_intel_signals.jsonl
STATUS_PATHS ['1_extracted/commentary_signals.jsonl', '1_extracted/market_intel_signals.jsonl']
```

produce_and_push:

```text
[2026-06-11T08:38:40+00:00] pushed 2 paths: l2(signals): nightly derived signals
VAULT_HEAD 307f8a4a
VAULT_ORIGIN_MAIN 307f8a4a3c20
```

结果: 通过。最终 vault 工作树干净, HEAD 与 origin/main 对齐。

### Step 3 投影验证

命令:

```bash
cd /root/policy-pipeline-src
/usr/bin/flock -w 7200 /var/lock/policy-pipeline-producer.lock \
  docker compose -f docker-compose.server.yml run --rm policy-pipeline \
  python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
```

关键输出:

```text
{"synced_count": 1176, "skipped_override_count": 0, "relation_count": 1649, "errors": [], "skipped_invalid_count": 15, "commentary_count": 186}
```

结果: 通过。`errors=[]`; `commentary_count=186` >= 171; `relation_count=1649` 保持 WP-2 基线。

### Step 4 安装 03:00 cron

偏差: runbook 中 03:00 原样长 cron 行被服务器 crontab 拒绝:

```text
"/tmp/tmp.eNpzsLaq0O":28: command too long
errors in crontab file, can't install.
CRON_COMMENTARY_SIGNALS_COUNT 0
```

处置: 将同一段 03:00 信号链逻辑落到 host state 脚本:

```text
/root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh
```

安装短 cron 行:

```cron
0 3 * * * /root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh >> /var/log/policy-pipeline/signals.log 2>&1
```

核验:

```text
CRON_COMMENTARY_SIGNALS_COUNT 1
0 3 * * * /root/policy-pipeline-state/bin/commentary_signals.run_nightly.sh >> /var/log/policy-pipeline/signals.log 2>&1
```

结果: 通过,但不是 runbook 原样长行。原因是系统 crontab 行长限制;脚本内容保留原 flock、notify、四段 docker 命令、apply 和 produce_and_push 白名单逻辑。

### Step 5 哨兵新口径实测

只读 sqlite token 判活:

```text
valid= True detail= 至少 1 个账号 token 有效 (1/1)
```

手跑 daily_check:

```json
{"checked": true, "relayed": false, "restored": true, "detail": "至少 1 个账号 token 有效 (1/1); feed_check=feed health ok: /feeds/all.atom HTTP 200", "qr_path": "", "checked_at": "2026-06-11T08:40:12.055247+00:00"}
```

结果: 通过。token 有效,未推码。

### 终态

- `/root/policy-pipeline-src` HEAD: `42608af`;与 `origin/main` 对齐。
- `/root/policy-vault` HEAD: `307f8a4a`;与 `origin/main` 对齐;工作树干净。
- root crontab 中 `commentary_signals.run` 计数: `1`。
- 远端 pipeline 工作树仍有既有 `scripts/**/__pycache__/` 未跟踪项;本次未清理。
- 原则/门禁: raw 未写; vault 写只经 `derived_signals apply` + `produce_and_push` 白名单; review queue 未被消费为 apply 清单; producer 操作持锁。

建议下一步: 明早检查 `/var/log/policy-pipeline/signals.log` 的 03:00 自动跑结果;若成功且无告警,可把 runbook 的超长 03:00 行改成脚本化接线,避免后续按原文复制再次触发 crontab 行长限制。
