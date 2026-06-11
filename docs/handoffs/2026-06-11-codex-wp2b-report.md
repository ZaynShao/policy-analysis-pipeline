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

## 续跑（resume）

时间：2026-06-11 15:31-15:33 CST
服务器：`root@8.216.59.173`
结论：**停在 Step 0 镜像重建，未进入 Step 1/2/3/4/5。**

### 红线状态

- 未打印 `/etc/policy-pipeline/*.env` 凭据值；本次未 source env。
- 未手工 `git add/commit` vault；未写 vault。
- 涉及 host module 的命令均在 `/root/policy-pipeline-src` 下执行。
- 未执行真跑 apply；未执行投影写状态；未安装 cron。
- 未触碰 `/root/safety-platform`、`platform-*`、tyo-prod、Mac wewe 容器。
- 执行时间为 15:31 CST 起，不在 07:00-10:30 CST 产线窗口。

### Step 0 · 部署

执行：

```bash
date "+%F %T %Z %z"
cd /root/policy-pipeline-src
git fetch --depth=1 origin main
git reset --hard origin/main
docker compose -f docker-compose.server.yml build policy-pipeline
docker run --rm policy-pipeline:latest git --version
docker run --rm policy-pipeline:latest sh -c "grep -c check_apply_gates /app/scripts/service/relations_increment.py"
```

关键输出：

```text
2026-06-11 15:31:19 CST +0800
HEAD is now at 9f78512 fix(docker): add git to runtime image for in-container vault reads
```

Docker build 失败：

```text
RUN apt-get update && apt-get install -y --no-install-recommends git ...
Setting up git (1:2.47.3-0+deb13u1) ...
RUN pip install --no-cache-dir -e .
WARNING: Retrying ... ReadTimeoutError ... /simple/httpcore/
ERROR: Cannot install anthropic because these package versions have conflicting dependencies.
The conflict is caused by:
    httpx 0.28.1 depends on httpcore==1.*
    ...
    httpx 0.23.0 depends on httpcore<0.16.0 and >=0.15.0
ERROR: ResolutionImpossible
failed to solve: process "/bin/sh -c pip install --no-cache-dir -e ." did not complete successfully: exit code: 1
```

镜像闸结果：

```text
docker run --rm policy-pipeline:latest git --version
docker: Error response from daemon: ... exec: "git": executable file not found in $PATH

docker run --rm policy-pipeline:latest sh -c "grep -c check_apply_gates /app/scripts/service/relations_increment.py"
2
```

判定：不通过。`policy-pipeline:latest` 未被成功重建；`git --version` 未输出版本号。`grep` 命中 2 次来自既有旧镜像，不能抵消重建失败。

### Step 1 · 状态校验

按修订要求，Step 1 仅在 Step 0 通过后执行。由于 Step 0 未通过，本步骤未作为续跑链路执行；只做停机后的只读复核，未重跑 `init-ledger`。

只读复核命令：

```bash
wc -l /root/policy-pipeline-state/sem_accepted_cumulative.jsonl
python3 -c "import json;print(len(json.load(open('/root/policy-pipeline-state/relations_pid_ledger.json'))['covered']))"
```

关键输出：

```text
SEM_LINES=537
LEDGER_COVERED=873
```

状态数仍符合修订期望，但因 Step 0 未过，未继续。

### Step 2 · 监督 dry-run

未执行。

原因：Step 0 镜像重建验证未通过，按“任何验证不过停下原样报告”执行。

### Step 3 · 真跑 apply + push

未执行。

原因：Step 2 未执行；未写 vault，未触发 `produce_and_push`。

### Step 4 · 投影验证

未执行。

原因：Step 3 未执行。

### Step 5 · 装 02:00 cron

未执行。

停机后复核：

```text
CRON_RELATIONS=0
CRON_POLICY=10
```

### 结束状态

远端源码：

```text
SRC_HEAD=9f78512e88723bbddbf8f83280d1945fd74fb601
```

远端源码工作树仍有此前运行产生的未跟踪 `__pycache__/`，未处理：

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

### 建议下一步

推荐路径：先修复 Docker build 的 Python 依赖可解析性，再重新执行本 resume 包的 Step 0。

理由：本次失败发生在镜像构建阶段的 `pip install --no-cache-dir -e .`，尚未进入关系 dry-run、judge、apply 或投影。当前 `pyproject.toml` 使用无上界依赖 `anthropic>=0.40`，构建时 pip 在解析 `anthropic` / `httpx` / `httpcore` 时失败；应在源码侧沉淀可重复构建的依赖约束后合 main，不建议在服务器上临时绕过。
