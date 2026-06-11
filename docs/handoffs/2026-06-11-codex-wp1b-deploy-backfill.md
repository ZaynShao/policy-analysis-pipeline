# Codex 交接：WP-1b 部署死信告警/sweep + 424 归属 backfill（服务器侧）

**前置**：WP-1a 已 Claude 审计通过（分支 `wp1/deadletter-alert-sweep`）。本包：合 main → 服务器部署 → cron 安装 → 投毒验证告警 → 424 backfill 分块 drain → 验收。
**服务器**：阿里云东京，Mac 上 `ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`。

**纪律（红线，违者中止）**：
- 凭据值**不打印、不进 git**（env 文件只看键名：`grep -oE '^[A-Z_]+=' <file>`）。微信 token 不碰。
- `/root/safety-platform`、`platform-*` 容器、tyo-prod(8.209.197.50)、Mac 的 wewe-rss 容器（保持停）**都不碰**。
- vault 写只经 `produce_and_push`（白名单守卫），**绝不**在 /root/policy-vault 手工 git add/commit。
- produce_and_push / notify / deadletter_* 是 host python module，**必须先 `cd /root/policy-pipeline-src`**。
- 手跑任何写 vault / 写 L2 队列的命令**必须持锁**：`flock /var/lock/policy-pipeline-producer.lock <cmd>`。
- 中文文件名 git 操作用 `-c core.quotepath=false`。
- 任何一步验证不过：**停下、原样报告输出**，不即兴绕。
- **时窗纪律**：drain 批次不得跨进次日 07:00–10:30 CST 产线窗口；当天做不完就停在批次边界，报告进度。

## Step 0 · 服务器部署（合 main 已由 Claude 完成：`bb52a6c` 已在 origin/main；无镜像重建）

服务器（新模块全在 host python 侧，容器代码零改动，**不需要 docker build**）：
```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main
# 验证闸:
python3 -c "from scripts.service.deadletter_alert import check_growth; from scripts.service.deadletter_sweep import plan_sweep; print('modules ok')"
```

## Step 1 · 安装 2 条 cron

从（已合 main 的）`docs/runbooks/s2-vps-cron.md` §1 **原样复制** 09:55 死信告警行 + 周日 08:30 sweep 行进 `crontab -e`（root）。其余行不动。
核验：`crontab -l | grep -c deadletter` 应为 2。

## Step 2 · 投毒验证告警（验收门：飞书真收到）

```bash
cd /root/policy-pipeline-src
echo '{"pid":"P_TEST_POISON","error":"poison test","ts":"2026-06-11T00:00:00+00:00"}' >> /root/policy-pipeline-state/l2_failures.jsonl
set -a; . /etc/policy-pipeline/notify.env; set +a
/usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state
```
判据：stdout `{"dead_count":1,"grew":true,"notified":true}`；**用户飞书收到死信告警**（报告里请用户确认）。
**清理（必做，防周日 sweep 把假 pid 回队）**：
```bash
rm /root/policy-pipeline-state/l2_failures.jsonl
/usr/bin/python3 -m scripts.service.deadletter_alert --state-dir /root/policy-pipeline-state   # 让 state 归 0,输出 grew:false
```

## Step 3 · 424 归属 backfill（分块,每块验证）

### 3.1 生成无 business_view 清单（host,只读 vault）
```bash
cd /root/policy-pipeline-src && python3 - <<'EOF'
import re, pathlib
vault = pathlib.Path('/root/policy-vault')
missing = []
for p in sorted((vault/'0_raw/policies').glob('*.md')):
    m = re.search(r'^id:\s*(\S+)', p.read_text(errors='ignore')[:2000], re.M)
    if m and not (vault/f'_meta/business_view/{m.group(1)}.yaml').exists():
        missing.append(m.group(1))
out = pathlib.Path('/root/policy-pipeline-state/backfill_20260611.txt')
out.write_text('\n'.join(missing))
print(f'missing business_view: {len(missing)}')
EOF
```
预期 ≈424（每日 cron 已消化的会少一点）。数字偏离 ±30 以上 → 停下报告。

### 3.2 分块入队 + drain（每块 ~100,首块为监督门）

每块流程（**整块持锁**；enqueue 用容器 python，沿用 2026-06-10 recover handoff 模式）：
```bash
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock bash -c '
  set -e
  CHUNK=$(sed -n "1,100p" /root/policy-pipeline-state/backfill_20260611.txt | tr "\n" "," | sed "s/,$//")
  docker compose -f docker-compose.server.yml run --rm -T policy-producer python - <<PYEOF
from pathlib import Path
from datetime import datetime, timezone
from scripts.service.l2_queue import enqueue_batch
pids = "$CHUNK".split(",")
enqueue_batch(Path("/state/l2_queue.jsonl"), pids, trigger="backfill_20260611", priority="normal", requested_at=datetime.now(timezone.utc).isoformat())
print(f"enqueued {len(pids)}")
PYEOF
  set -a; . /etc/policy-pipeline/notify.env; set +a
  docker compose -f docker-compose.server.yml run --rm policy-producer python -m scripts.service.run_l2 \
    --vault /vault --state-dir /state \
    --gen-model deepseek-v4-flash --gen-provider openai \
    --judge-model deepseek-v4-flash --judge-provider openai
  /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
    --whitelist 1_extracted/,_meta/business_view/,2_crystallized/ --message "l2: backfill batch"
'
# 块后核验:
wc -l /root/policy-pipeline-state/l2_queue.jsonl 2>/dev/null || echo "queue empty"
wc -l /root/policy-pipeline-state/l2_failures.jsonl 2>/dev/null || echo "no deadletter"
ls /root/policy-vault/_meta/business_view/ | wc -l
sed -i "1,100d" /root/policy-pipeline-state/backfill_20260611.txt   # 消掉已处理段
```

- **首块 = 监督门**：run_l2 输出 `{"processed":N,"ok":X,"failed":Y}`，failed/processed > 10% → **停下报告**（带死信样例），不进下一块。
- 之后每块照跑；每块报告一行：`batch N: ok X failed Y bv_total Z`。
- 死信会触发 09:55 告警 cron——预期行为，报告里说明即可。市监失效类噪声政策若失败属预期（L1 gate 域问题，S3 处置）。

### 3.3 收尾投影 + 总验收
```bash
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm \
  policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
head -c 400 /root/policy-pipeline-state/last_sync_run.json; echo
```
判据：`synced_count` ≈ 1200±30（= 旧 800 + backfill 成功数 − skipped_invalid）；`errors:[]`；`relation_count` **应 > 992**（部分悬挂边因端点政策入库而恢复——记录恢复了多少，这是 WP-2 的基线数字）。
vault 干净：`git -C /root/policy-vault status --short` 空、HEAD==origin/main。

## 回报格式

逐 Step：命令 + 关键输出（env 值打码）。重点：Step 2 飞书是否真收到、3.2 每块一行数据、3.3 终态 json、死信终量与样例、偏差。报告落 `docs/handoffs/2026-06-11-codex-wp1b-report.md`（不含凭据值），**commit 仅点名该报告文件**。
