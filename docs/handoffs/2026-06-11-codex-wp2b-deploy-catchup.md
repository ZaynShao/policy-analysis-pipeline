# Codex 交接：WP-2b ③关系增量上云部署 + 361 篇补课（服务器侧）

**前置**：WP-2a 已 Claude 审计合 main。本包：服务器部署（**需重建镜像**，relations_increment 跑在容器内）→ 状态初始化（seed + pid ledger）→ 监督 dry-run 钉数 → 真跑 apply + push → 投影验证 → 装 02:00 cron。
**服务器**：`ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173`。

**纪律（红线，违者中止）**：凭据值不打印不进 git；vault 写只经编排器 apply + `produce_and_push`，绝不手工 git add/commit vault；host module 必先 `cd /root/policy-pipeline-src`；**真跑（写 vault/状态）必持 `flock /var/lock/policy-pipeline-producer.lock`**；别碰 `/root/safety-platform`、`platform-*`、tyo-prod、Mac wewe 容器；不跨进 07:00–10:30 CST 产线窗口；任何验证不过停下原样报告。

## Step 0 · 部署（镜像必须重建——容器内跑新模块）

```bash
cd /root/policy-pipeline-src && git fetch --depth=1 origin main && git reset --hard origin/main
docker compose -f docker-compose.server.yml build policy-pipeline   # 注意是 policy-pipeline(有 build 字段),不是 policy-producer
# 镜像验证闸(过了才往下):
docker run --rm policy-pipeline:latest sh -c "grep -c check_apply_gates /app/scripts/service/relations_increment.py"   # ≥1
```

## Step 1 · 状态初始化（幂等：已存在则跳过并报告）

```bash
# 1a. 语义 accepted 种子(537 行,git 随 pull 到位)
test -f /root/policy-pipeline-state/sem_accepted_cumulative.jsonl && echo "seed 已存在,跳过" || \
  cp /root/policy-pipeline-src/state/node3c/sem_accepted_20260606_seed.jsonl /root/policy-pipeline-state/sem_accepted_cumulative.jsonl
wc -l /root/policy-pipeline-state/sem_accepted_cumulative.jsonl   # 期望 537

# 1b. pid ledger:以 6/6 重建语料为基线(哨兵 venv 有全部依赖)
cd /root/policy-pipeline-src && /root/policy-sentinel-venv/bin/python -m scripts.service.relations_increment init-ledger \
  --vault /root/policy-vault --state-dir /root/policy-pipeline-state \
  --as-of-commit a6fb3c09c531e31a04941701b8be4951cb884039
# 期望 {"covered": ≈863}。偏离 ±30 → 停下报告。
```

## Step 2 · 监督 dry-run（真 judge 花钱,deepseek 量级 ~407 对,可接受;判定结果落 judged ledger,真跑不重花）

```bash
set -a; . /etc/policy-pipeline/notify.env; set +a
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.relations_increment run --vault /vault --state-dir /state \
  --judge-model deepseek-v4-flash --judge-provider openai --dry-run
```
**监督门**（任一不过 → 停下报告，不进 Step 3）：
- `new_pids` ≈ 361±30；
- `judged` ≈ 数百量级（WP-0 估 407；±50% 内可接受，因语料与口径有日差）；
- `canonical_edges` ≥ 1138×0.85 ≈ 967 且大体 ≥ 1138（只增不减预期；少量回落可解释——6/10 清理掉的 15 条脏政策的旧边会被全量重生剔除）。把三个数与 accepted 数贴报告。

## Step 3 · 真跑 apply + push（持锁）

```bash
set -a; . /etc/policy-pipeline/notify.env; set +a
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock bash -c '
  set -e
  docker compose -f docker-compose.server.yml run --rm policy-producer \
    python -m scripts.service.relations_increment run --vault /vault --state-dir /state \
    --judge-model deepseek-v4-flash --judge-provider openai
  /usr/bin/python3 -m scripts.service.produce_and_push --vault-dir /root/policy-vault \
    --whitelist 1_extracted/relations/ --message "l2(relations): catch-up increment (361 pids since 6/6)"
'
```
判据：run 输出 `applied:true`；produce_and_push exit 0 pushed N paths；`git -C /root/policy-vault status --short` 干净且 HEAD==origin/main。

## Step 4 · 投影验证（持锁手跑一次 run_sync）

```bash
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm \
  policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
head -c 400 /root/policy-pipeline-state/last_sync_run.json; echo
```
判据：`errors:[]`；`relation_count` **> 1123**（昨基线;增幅 = 新边数−悬挂）。记录终值,这是 hengguan 端可见关系的新基线。

## Step 5 · 装 02:00 cron

从（已合 main 的）`docs/runbooks/s2-vps-cron.md` §1 **原样复制** 02:00 ③关系增量行进 root crontab。其余行不动。
核验：`crontab -l | grep -c relations_increment` == 1；`crontab -l | grep -c policy` 总数比之前 +1。

## 回报

逐 Step 命令+关键输出（env 值打码）。重点：Step 2 三数、Step 3 applied/push、Step 4 relation_count 终值、偏差。报告落 `docs/handoffs/2026-06-11-codex-wp2b-report.md`（commit 仅点名该文件）。
