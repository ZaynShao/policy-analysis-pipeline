# Codex 交接：WP-3b ③信号线服务器部署 + 监督首跑（服务器侧）

**前置**：WP-3a 已审计合 main（`c638cef`）。本包：部署 → manifest 初始化 → 监督跑一次完整信号链 → 投影验证 → 装 03:00 cron → 哨兵新口径实测。
**服务器**：`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`。

**纪律（红线，违者中止）**：凭据值不打印不进 git；vault 写只经 `derived_signals apply` + `produce_and_push` 白名单，绝不手工 git add/commit vault；host module 必先 `cd /root/policy-pipeline-src`；真跑必持 `flock /var/lock/policy-pipeline-producer.lock`；别碰 `/root/safety-platform`、`platform-*`、tyo-prod、Mac wewe 容器；不跨进 07:00–10:30 CST 产线窗口；任何验证不过停下原样报告。

## Step 0 · 部署（**不重建镜像**）

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main   # 期望 HEAD=c638cef
```

不重建镜像的依据：本链所需容器模块在现镜像（`9f78512` 构建）中与 main 行为一致——`market_intel_signals` 唯一改动是 `--manifest` 默认值，而本包与 cron 行都显式传 `--manifest`；哨兵/produce_and_push 是 host 侧，直接用 checkout。验证闸：

```bash
docker run --rm policy-pipeline:latest python -c "import scripts.commentary_signals.run, scripts.market_intel_signals.run, scripts.derived_signals.run; print('IMAGE_OK')"
```

## Step 1 · manifest 初始化（幂等）

```bash
mkdir -p /root/policy-pipeline-state/source_ready
test -f /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl && echo "已存在,跳过" || \
  cp /root/policy-pipeline-src/state/source_ready/market_intel_manifest.jsonl /root/policy-pipeline-state/source_ready/
wc -l /root/policy-pipeline-state/source_ready/market_intel_manifest.jsonl   # 期望 23
```

## Step 2 · 监督首跑（持锁，按 runbook 03:00 行拆四段跑，逐段记录 summary）

四段命令照 `docs/runbooks/s2-vps-cron.md` §1 的 03:00 行拆开（路径 flag 原样），整体包在 `flock /var/lock/policy-pipeline-producer.lock bash -c '...'` 内顺序执行，最后跑 `produce_and_push --whitelist "1_extracted/commentary_signals.jsonl,1_extracted/market_intel_signals.jsonl"`。

**监督门**（任一不过 → 停下报告）：
- commentary dry-run：signals 数 > 0（评论存量百量级，为 0 即异常）；记录 signals/queue 两数；
- market dry-run：summary 中 manifest 行全部表示为 signal 或 queue（spec Done Gate），记录两数；
- derived preview：记录 accepted commentary / accepted market / blocked 三数；
- apply 后：`git -C /root/policy-vault status --short` **只**出现两个白名单文件；
- produce_and_push exit 0（`pushed` 或 `no change, skip` 均可，记录是哪种）；之后 vault 干净且 HEAD==origin/main。

## Step 3 · 投影验证（持锁手跑 run_sync）

照 WP-2b Step 4 原样。判据：`errors=[]`；记录 `commentary_count`（基线 171，预期 ≥171）与 `relation_count`（应保持 1649，信号链不该动关系）。

## Step 4 · 装 03:00 cron

从 runbook §1 **原样复制** 03:00 信号链行进 root crontab，其余行不动。核验：`crontab -l | grep -c "commentary_signals.run"` == 1。

## Step 5 · 哨兵新口径实测（host venv）

```bash
cd /root/policy-pipeline-src
# 先确认 token 当前有效(只读 sqlite):
/root/policy-sentinel-venv/bin/python -c "from scripts.l1_collect.commentary_ingest.qr_relay.detector import token_needs_relay; from pathlib import Path; s=token_needs_relay(Path('<sqlite 路径按 09:30 cron 行实际参数>')); print('valid=',s.valid,'detail=',s.detail)"
```

token valid 时手跑一次 daily_check（照 09:30 cron 行命令）应为安全 no-op：期望输出"判活通过、不推码"，且 detail 含 token 口径（可附 feed_check 诊断）。若 token 实测无效 → **不要继续**，停下报告（推码涉及用户扫码）。

## 回报

逐 Step 命令+关键输出（env 值打码）。重点：Step 2 各段数字、Step 3 commentary_count/relation_count、Step 5 detail 字符串。报告落 `docs/handoffs/2026-06-11-codex-wp3b-report.md`（commit 仅点名该文件）。
