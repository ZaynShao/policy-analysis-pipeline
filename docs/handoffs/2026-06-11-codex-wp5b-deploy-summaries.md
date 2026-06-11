# Codex 交接：WP-5b summaries 服务器部署 + 存量规范化 + 回填（服务器侧）

**前置**：WP-5a 已审计合 main（`50e5de0`）。本包：部署（重建镜像）→ 存量 934 行规范化 → 回填（dry-run 钉数+抽样质检 → 真跑 apply+push）→ 装 04:00 cron。
**服务器**：`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`。

**纪律（红线，违者中止）**：凭据值不打印不进 git；vault 写只经模块 init-ledger --apply / run apply + `produce_and_push` 白名单 `1_extracted/policy_summaries.jsonl`；真跑（写 vault/state）必持 `flock /var/lock/policy-pipeline-producer.lock`；别碰 safety-platform / platform-* / tyo-prod / Mac wewe；不跨进 07:00–10:30 CST 窗口；任何验证不过停下原样报告。

## Step 0 · 部署（重建镜像——容器要跑新模块）

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main   # 期望 HEAD=50e5de0
docker compose -f docker-compose.server.yml build policy-pipeline
# pip 网络超时失败:等 ≥60s 重试,最多 3 次;3 次同因失败停下报告
docker run --rm policy-pipeline:latest python -c "import scripts.service.summaries_increment as m; print('IMAGE_OK')"
```

## Step 1 · 存量规范化（持锁）

```bash
# 1a. 先看报告(不写):
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.summaries_increment init-ledger --vault /vault --state-dir /state
```
**门**：kept_direct ≈ 696±20；quarantined ≤ 238；covered = kept_direct+kept_alias（数字自洽）。过门才执行：
```bash
# 1b. 应用 + push:
flock /var/lock/policy-pipeline-producer.lock bash -c '
  set -e
  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.service.summaries_increment init-ledger --vault /vault --state-dir /state --apply
  /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
    --whitelist 1_extracted/policy_summaries.jsonl --message "l2(summaries): normalize legacy policy ids"
'
```
判据：push exit 0；vault 干净；`wc -l` vault 文件 == covered；ledger covered 数与报告一致。

## Step 2 · 回填 dry-run（真 LLM 花钱；staging 缓存防重花）

```bash
set -a; . /etc/policy-pipeline/notify.env; set +a
cd /root/policy-pipeline-src
# 2a. 小批抽样:
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.summaries_increment run --vault /vault --state-dir /state \
  --model deepseek-v4-flash --provider openai --dry-run --limit 20
```
**抽样质检门**：cat staging 前 3 行——summary 为通顺中文 2-3 句、one_liner/reading_value ≤25 字且非空、policy_id 真实存在。质量异常 → 停下报告。
```bash
# 2b. 全量 dry-run(预计 new ≈ 1213−covered;若 new > 700 停下报告;串行 LLM 可能跑 40-60 分钟,耐心等):
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.summaries_increment run --vault /vault --state-dir /state \
  --model deepseek-v4-flash --provider openai --dry-run
```
**门**：staged + queued ≈ new（自洽）；queued 占比 <10%（异常高=prompt/数据问题，停下报告）。

## Step 3 · 真跑 apply + push（持锁；staging 已就绪，不再调 LLM）

```bash
flock /var/lock/policy-pipeline-producer.lock bash -c '
  set -e
  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.service.summaries_increment run --vault /vault --state-dir /state \
    --model deepseek-v4-flash --provider openai
  /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
    --whitelist 1_extracted/policy_summaries.jsonl --message "l2(summaries): backfill batch"
'
```
判据：`applied:true`；push exit 0；vault 干净 HEAD==origin；`wc -l` == ledger covered 数；python 一行校验无重复 policy_id。

## Step 4 · 装 04:00 cron

runbook §1 原样复制 04:00 行。核验 `crontab -l | grep -c summaries_nightly` == 1。

## 回报

逐 Step 命令+关键输出（env 打码）。重点：Step 1a 报告四数、Step 2 抽样 3 行原文+全量三数、Step 3 终态行数、queue 数。报告落 `docs/handoffs/2026-06-11-codex-wp5b-report.md`（commit 仅点名该文件，不 push）。
