# WP-2b ③关系增量上云部署 + 361 篇补课报告

时间：2026-06-11 15:21-15:32 CST  
服务器：`root@8.216.59.173`  
结论：**停在 Step 2 dry-run，未进入 apply/push、投影验证或 cron 安装。**

## 红线状态

- 未打印 `/etc/policy-pipeline/*.env` 凭据值。
- 未手工 `git add/commit` vault；未写 vault。
- 涉及 host module 的命令均在 `/root/policy-pipeline-src` 下执行。
- 写状态/真跑相关命令使用了 `flock /var/lock/policy-pipeline-producer.lock`。
- 未触碰 `/root/safety-platform`、`platform-*`、tyo-prod、Mac wewe 容器。
- 执行时间为 15:21 CST 起，不在 07:00-10:30 CST 产线窗口。

## Step 0 · 部署

执行：

```bash
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
docker compose -f docker-compose.server.yml build policy-pipeline
docker run --rm policy-pipeline:latest sh -c "grep -c check_apply_gates /app/scripts/service/relations_increment.py"
```

关键输出：

```text
HEAD is now at 11424f1 docs(relations): document increment runbook
Image policy-pipeline:latest Built
IMAGE_GATE_COUNT=2
```

判定：通过。`check_apply_gates` 命中 2 次，满足 ≥1。

## Step 1 · 状态初始化

执行：

```bash
test -f /root/policy-pipeline-state/sem_accepted_cumulative.jsonl && echo "seed 已存在,跳过" || \
  cp /root/policy-pipeline-src/state/node3c/sem_accepted_20260606_seed.jsonl /root/policy-pipeline-state/sem_accepted_cumulative.jsonl
wc -l /root/policy-pipeline-state/sem_accepted_cumulative.jsonl
cd /root/policy-pipeline-src
/root/policy-sentinel-venv/bin/python -m scripts.service.relations_increment init-ledger \
  --vault /root/policy-vault --state-dir /root/policy-pipeline-state \
  --as-of-commit a6fb3c09c531e31a04941701b8be4951cb884039
```

关键输出：

```text
seed copied
SEED_LINES=537
```

第一次 ledger 初始化失败：

```text
fatal: not a tree object: a6fb3c09c531e31a04941701b8be4951cb884039
tarfile.ReadError: empty file
```

诊断为 `/root/policy-vault` 缺少该历史 commit 对象；vault 工作树当时干净。只执行 git 对象补齐：

```bash
git -C /root/policy-vault fetch --deepen=100 origin main
```

重跑后输出：

```text
ASOF_PRESENT_AFTER_FETCH=yes
{"covered": 873}
```

判定：通过。seed 为 537 行；`covered=873`，在 863±30 范围内。

## Step 2 · 监督 dry-run

执行：

```bash
set -a; . /etc/policy-pipeline/notify.env; set +a
cd /root/policy-pipeline-src
flock /var/lock/policy-pipeline-producer.lock docker compose -f docker-compose.server.yml run --rm policy-producer \
  python -m scripts.service.relations_increment run --vault /vault --state-dir /state \
  --judge-model deepseek-v4-flash --judge-provider openai --dry-run
```

失败输出：

```text
FileNotFoundError: [Errno 2] No such file or directory: 'git'
```

失败位置：

```text
/app/scripts/analysis_high_precision_relations/run.py
_run_git(vault, ["ls-files", "--", "0_raw/policies/*.md"])
```

原因：`policy-producer` 使用 `policy-pipeline:latest` 镜像；该镜像由当前 `Dockerfile` 构建，但容器内没有 `git` 可执行文件。远端复核：

```text
COMPOSE_POLICY_PRODUCER:
  policy-producer:
    image: policy-pipeline:latest

DOCKERFILE_GIT_LINES:
  <empty>
```

判定：不通过。dry-run 未产出 `new_pids`、`judged`、`canonical_edges`，因此未进入 Step 3。

## Step 3 · 真跑 apply + push

未执行。

原因：Step 2 dry-run 未通过，按“任一不过 → 停下报告，不进 Step 3”执行。

## Step 4 · 投影验证

未执行。

原因：Step 3 未执行。

## Step 5 · 装 02:00 cron

未执行。

复核：

```text
CRON_RELATIONS=0
CRON_POLICY=10
```

## 结束状态

远端源码：

```text
SRC_HEAD=11424f139898b466d6610d061a6ccd8cb7c101ad
```

远端源码工作树有运行产生的未跟踪 `__pycache__/`，未处理：

```text
?? scripts/__pycache__/
?? scripts/analysis_high_precision_relations/__pycache__/
?? scripts/analysis_relation_views/__pycache__/
?? scripts/analysis_semantic_relations/__pycache__/
?? scripts/l1_audit/__pycache__/
?? scripts/l1_collect/__pycache__/
?? scripts/l1_collect/commentary_ingest/__pycache__/
?? scripts/l1_collect/commentary_ingest/qr_relay/__pycache__/
?? scripts/service/__pycache__/
```

vault：

```text
VAULT_HEAD=9dd43e2d1f50eb55e7106c60c6b0a68473ea7f6a
VAULT_ORIGIN=9dd43e2d1f50eb55e7106c60c6b0a68473ea7f6a
git -C /root/policy-vault status --short
<empty>
```

## 建议下一步

推荐路径：先修镜像运行时依赖，让 `policy-pipeline:latest` 包含 `git`，再从 Step 0 重建镜像后重跑 Step 2。

理由：失败发生在 dry-run 读取 vault tracked policy 文件列表前，尚未进入业务判定；修复点是容器运行时依赖，不是关系规则或数据偏差。修复合 main 后，按本包从 Step 0 重新执行即可；Step 1 的 seed 和 ledger 初始化是幂等的，ledger 当前已达到 `covered=873`。
