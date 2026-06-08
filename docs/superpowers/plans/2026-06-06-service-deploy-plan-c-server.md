# Plan C · 服务器部署 实施计划（v2 · 容器版 · 按 2026-06-07 实测重写）

> **配套 spec：** `docs/superpowers/specs/2026-06-06-service-deploy-design.md`。
> **v2 变更（2026-06-07 服务器实测后重写）：** 原 v1 的 `host + systemd + /data + venv + 全新 PG` 假设**作废**。实测发现：heng-guan 全栈已 Docker Compose 部署在服务器并在跑、PostgreSQL 在容器网络内（未暴露 host）、host 是 Python 3.14（psycopg2-binary wheel 风险）。**用户已拍：pipeline 做成 Docker 容器、挂现有 `safety-platform_platform-net` 网络。** 本文按此重写。
> **infra「测试」= 部署后运行态检查**（`docker ps`/`docker logs`/`docker exec psql`），不是 TDD 单测。
> **密钥已装**：`~/.ssh/aliyun-tokyo-20260606.pem`（本机），服务器 root 免密。

**Goal:** 把 pipeline（Plan A）做成 Docker 容器跑在服务器，挂 `safety-platform_platform-net`，用服务名 `heng-pg:5432` 写库；vault 从 Mac rsync 上 host 后挂载；凭据 out-of-git 注入；首次 sync 走「清空替换」把生产 Policy 换成 pipeline 的 836 篇高精度数据。

---

## 勘察结果（实测 2026-06-07，替代 v1 全部 `<待核实>`）

| 项 | 实测值 |
|---|---|
| 主机 | `8.216.59.173`（root，key 免密），hostname iZ6wecu0oetc429yglu0cjZ |
| OS / 资源 | Ubuntu 26.04，systemd 259，4 核 / 7.1Gi RAM，**磁盘 40G 用 90%、剩 4.0G（紧）** |
| host Python | **3.14.4**（→ 不在 host 跑 pipeline，psycopg2-binary 可能无 wheel；容器内钉 3.12） |
| heng-guan | **已全栈 Docker 部署在跑**：`platform-heng-backend/heng-frontend/heng-pg` + kb 栈 + guardian/intel-center + `platform-nginx`(:80)。仓在 `/root/safety-platform` |
| **heng-pg** | 容器 `platform-heng-pg`（pgvector/pgvector:pg15，healthy），网络 `safety-platform_platform-net`（bridge），**5432 不暴露 host**。DB=`hengguan` user=`heng` pass=**见 `/etc/policy-pipeline/pipeline.env`，不入仓** |
| backend 连库串 | `postgresql://heng:<pass>@heng-pg:5432/hengguan?schema=public`（服务名连）→ pipeline 容器同法 |
| Prisma schema | `/root/safety-platform/services/heng-guan/backend/prisma/schema.prisma`（535 行；enum PolicyImportance 已有 STRATEGIC/MAJOR/GENERAL/INFO；Policy.importance 已有；零 @map；3 新表 + 8 pipeline 字段待迁移） |
| 生产 Policy 数据 | **50 条真演示**（AUTO34/MANUAL16，152 PolicyTag/163 Visit/2 Monthly，PolicyRelation 0）→ **用户决策：清空替换**（pipeline 成唯一权威，Route C 本意） |
| egress | github 200 / api.minimaxi.com / api.deepseek.com / dashscope 全可达。TZ Asia/Shanghai +0800 |
| vault | **服务器上还没有** → Phase 1 从 Mac `rsync` 上去（~144M 工作树）。**P2（vault GitHub remote）Phase 1 不需要**（rsync 绕开；L1 服务化后才需 remote 以便 append 回推） |

---

## 架构（v2）

```
Mac vault ──rsync──▶ /root/policy-vault (host, ro 挂进容器)
                                │
  pipeline 仓 ─clone─▶ /root/policy-pipeline ─docker build─▶ 镜像(python:3.12-slim)
                                │
            docker compose (pipeline 仓 docker-compose.server.yml)
                 service: policy-pipeline
                 networks: [platform-net (external: safety-platform_platform-net)]
                 env_file: /etc/policy-pipeline/pipeline.env  (DATABASE_URL + 模型 key, 600)
                 volumes:
                   - /root/policy-vault:/vault:ro
                   - /root/policy-pipeline-state:/state
                                │
        L2 worker: python -m scripts.service.run_l2  (drain_queue → 归属 → 排空触发 sync)
        sync:      run_sync → heng-pg:5432/hengguan upsert
```

- **连库**：容器内 `DATABASE_URL=postgresql://heng:<pass>@heng-pg:5432/hengguan?schema=public`（同 backend，靠 platform-net 服务名解析）。
- **Python**：镜像钉 `python:3.12-slim`（psycopg2-binary 有 wheel），绕开 host 3.14。
- **触发**：Phase 1 — L2/sync 用 `docker compose run` 手动或 host cron；L1 占位（频率待 TODO 闭环）。
- **凭据**：`/etc/policy-pipeline/pipeline.env`（host，600，env_file 注入，不入仓）。

---

## Task 0: 服务器勘察 ✅ 已完成（2026-06-07）

实测值见上「勘察结果」表，已替代全部 v1 占位。本任务关闭。

---

## Task 1: pipeline 容器化（Dockerfile + compose，pipeline 仓）

**Files（pipeline 仓，feat/service-deploy）:**
- Create: `Dockerfile`
- Create: `docker-compose.server.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Dockerfile（钉 py3.12）**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .
# vault 与 state 运行时挂载，不进镜像
ENV PYTHONUNBUFFERED=1
```

- [ ] **Step 2: docker-compose.server.yml（挂 external 网络）**

```yaml
services:
  policy-pipeline:
    build: .
    image: policy-pipeline:latest
    container_name: policy-pipeline
    env_file: /etc/policy-pipeline/pipeline.env
    volumes:
      - /root/policy-vault:/vault:ro
      - /root/policy-pipeline-state:/state
    networks: [platform-net]
    # 默认不常驻;用 `docker compose run` 跑 L2/sync。L2 常驻化留 Task 5。
    command: ["python", "-m", "scripts.service.run_l2",
              "--vault", "/vault", "--state-dir", "/state",
              "--gen-model", "MiniMax-M2.7-highspeed", "--gen-provider", "anthropic",
              "--judge-model", "deepseek-v4-flash", "--judge-provider", "openai"]
    restart: "no"

networks:
  platform-net:
    external: true
    name: safety-platform_platform-net
```

- [ ] **Step 3: .dockerignore**（排除 .git/tests/state/docs/.venv 等，控镜像体积——磁盘紧）

> **接线点（Plan A 需补，无新逻辑）：** `scripts/service/run_l2.py` CLI wrapper（读 env → 构造 `make_attribution_runner` + sync runner → `drain_queue`）。**Plan A 收尾时补**（见 Plan A 补线）。

---

## Task 2: vault 上 host（rsync）+ 凭据 env（out-of-git）

- [ ] **Step 1: vault rsync（Mac → host，绕开 P2）**

```bash
# 本机执行;~144M 工作树,不带 .git
rsync -az --delete --exclude='.git' \
  -e "ssh -i ~/.ssh/aliyun-tokyo-20260606.pem" \
  "/Users/shaoziyuan/Documents/Zayn Main/政策分析/" \
  root@8.216.59.173:/root/policy-vault/
ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173 \
  'ls /root/policy-vault/_meta/business_view/*.yaml | wc -l'
```
Expected: business_view yaml 数 ≈ 836（②-B apply 后）/ 当前 ≈ 当下 vault 实际数。

- [ ] **Step 2: 凭据 env（不进仓，scp）**

```bash
# 本机:基于 ~/.config/policy-pipeline/models.env 造服务器版,加 DATABASE_URL
# DATABASE_URL=postgresql://heng:<heng-pg pass>@heng-pg:5432/hengguan?schema=public
scp -i ~/.ssh/aliyun-tokyo-20260606.pem <本地拼好的 pipeline.env> \
  root@8.216.59.173:/etc/policy-pipeline/pipeline.env
ssh -i ~/.ssh/aliyun-tokyo-20260606.pem root@8.216.59.173 \
  'mkdir -p /etc/policy-pipeline; chmod 600 /etc/policy-pipeline/pipeline.env'
```
> `pipeline.env` 含 ANTHROPIC_*（gen=MiniMax）/ OPENAI_*（judge=deepseek 端点）/ DATABASE_URL。**绝不入任何 git 仓、不进镜像。**

- [ ] **Step 3: 磁盘预算确认**（vault 144M + 镜像 ~250M + state，剩 4G 够但要看）

```bash
ssh ... 'df -h /; du -sh /root/policy-vault'
```

---

## Task 3: Plan B 迁移上生产库（备份先）+ 清空替换 cutover

> **依赖 Plan B Task 1**（schema.prisma 加 8 字段 + 3 表，生成 migration，PR 给管理员）。本任务=把它**应用到线上 `hengguan`**。
> **顺序铁律：备份 → 迁移 → 清空替换 → 首次 sync。**

- [ ] **Step 1: 备份生产库（强制，先于任何写）**

```bash
ssh ... 'docker exec platform-heng-pg pg_dump -U heng -d hengguan -Fc \
  -f /tmp/hengguan_pre_pipeline_$(date +%Y%m%d).dump && \
  docker cp platform-heng-pg:/tmp/hengguan_pre_pipeline_*.dump /root/'
```
Expected: dump 文件存在（回滚靠它）。

- [ ] **Step 2: 应用 Prisma 迁移到生产库**

```bash
# safety-platform 仓更新（含 Plan B 的 migration）已 pull 到 /root/safety-platform 后:
ssh ... 'docker exec platform-heng-backend npx prisma migrate deploy'
# 校验新表/列存在
ssh ... 'docker exec platform-heng-pg psql -U heng -d hengguan -c "\d \"Policy\"" | grep -E "pipelinePid|importanceOverride"'
```
Expected: 迁移成功；Policy 出现 pipelinePid/importanceOverride 等列；3 新表建立。
> 新字段全 nullable、新表独立 → 迁移对现有 50 行无破坏（破坏发生在下一步「清空替换」，故备份在 Step 1）。

- [ ] **Step 3: 清空替换 cutover（用户决策）**

```bash
# 清空现有 50 条演示 Policy（级联 tag/visit/...）,让 pipeline 成唯一权威
ssh ... 'docker exec platform-heng-pg psql -U heng -d hengguan \
  -c "TRUNCATE \"Policy\" RESTART IDENTITY CASCADE;"'
ssh ... 'docker exec platform-heng-pg psql -U heng -d hengguan -tAc "SELECT count(*) FROM \"Policy\";"'
```
Expected: count = 0。
> 级联会清掉 PolicyTag(152)/Visit(163)/Monthly(2) 等演示交互数据——**用户已确认可弃**（Route C：pipeline 是权威，PR 时前端团队会看到）。

---

## Task 4: build 镜像 + 首次 sync 验证

- [ ] **Step 1: clone pipeline + build**

```bash
ssh ... 'cd /root && git clone -b feat/service-deploy <pipeline-git-remote> policy-pipeline && \
  cd policy-pipeline && docker compose -f docker-compose.server.yml build'
```
> **接线点 P-remote**：pipeline 仓需有服务器可达的 git remote（origin 是 github.com/ZaynShao/policy-analysis-pipeline，feat/service-deploy 需 push 上去；当前是本地分支）。push 前先按「分支衔接」rebase onto origin/main。

- [ ] **Step 2: 首次 sync（只跑 sync，不跑 L2）**

```bash
ssh ... 'cd /root/policy-pipeline && docker compose -f docker-compose.server.yml run --rm \
  policy-pipeline python -m scripts.sync.run_sync \
  --vault /vault --state-dir /state --pipeline-version 1'
ssh ... 'cat /root/policy-pipeline-state/last_sync_run.json'
```
Expected: `synced_count` ≈ 836（②-B 数据；③-C 未 apply → relation_count 0，见 P3 + CONTRACT-REL-1）；errors 空或可解释。

- [ ] **Step 3: DB 校验**

```bash
ssh ... 'docker exec platform-heng-pg psql -U heng -d hengguan -tAc \
  "SELECT count(*) FROM \"Policy\" WHERE \"pipelinePid\" IS NOT NULL;"'
```
Expected: ≈ 836。前端列表/详情应能看到 pipeline 数据（Plan B 端点联调）。

---

## Task 5: L2 worker 触发（Phase 1 简版）

> L1 占位（spec §8 TODO：频率/方法/SOP 剥离未启动）。Phase 1 先把 L2+sync 跑通；L2 由手动/cron 触发，不挂常驻守护。

- [ ] **Step 1: 手动触发 L2 一轮（队列有 pid 时）**

```bash
ssh ... 'cd /root/policy-pipeline && docker compose -f docker-compose.server.yml run --rm policy-pipeline'
# 默认 command 即 run_l2:drain_queue → 排空触发 sync
```
Expected: 队列空时优雅空转（drain_queue 空不触发 sync）；有 pid 时跑归属增量→写账本→sync。

- [ ] **Step 2: （可选）host cron 周期触发 sync**（频率待定，先记不配）

```
# /etc/cron.d/policy-pipeline （示例,频率 TODO 闭环后再启用）
# 0 */6 * * * root cd /root/policy-pipeline && docker compose -f docker-compose.server.yml run --rm policy-pipeline python -m scripts.sync.run_sync --vault /vault --state-dir /state --pipeline-version 1
```

- [ ] **Step 3: 防重叠**（L1 服务化时才需，记约定）：cron tick 先读 l1_status，running 跳过；run_pipeline 入口 `is_running()` 守卫（Plan A 补线）。

---

## Task 6: 验收 + 回滚预案

- [ ] **Step 1: 端到端验收**

```bash
ssh ... '
  echo "=== image ==="; docker images | grep policy-pipeline
  echo "=== last sync ==="; cat /root/policy-pipeline-state/last_sync_run.json
  echo "=== policy count ==="; docker exec platform-heng-pg psql -U heng -d hengguan -tAc "SELECT count(*) FROM \"Policy\";"
  echo "=== creds 600 ==="; stat -c "%a" /etc/policy-pipeline/pipeline.env'
```

- [ ] **Step 2: 前端联调（Plan B）** — heng-guan 列表/详情看到 pipelinePid 非空政策；改分（importanceOverride）→ 再 sync 不被踩；手动录入走通（Plan B poller）。

- [ ] **Step 3: 回滚预案（记录）**

```
回滚点：
- DB（最重要）：docker exec -i platform-heng-pg pg_restore -U heng -d hengguan --clean /root/hengguan_pre_pipeline_*.dump
  （Step 1 的备份；清空替换是破坏性操作，回滚全靠它）
- Prisma 迁移：prisma migrate resolve --rolled-back + 反向 SQL（新表 DROP、Policy 新列 DROP，均 nullable/独立）
- 容器：docker compose -f docker-compose.server.yml down；docker image rm policy-pipeline
- vault/state/凭据：rm -rf /root/policy-vault /root/policy-pipeline-state /etc/policy-pipeline/pipeline.env
关键：sync 只 upsert pipeline 字段（pipelinePid 等）；但「清空替换」TRUNCATE 是破坏性的 → 备份(Step1)是唯一安全网,务必先做。
```

---

## Self-Review（对 spec + 实测核对）

**v2 与实测一致：**
- 运行形态 = Docker 容器挂 platform-net（用户拍）→ Task 1 ✓
- 连库 = heng-pg:5432/hengguan 服务名（实测 backend 同法）→ 架构 + Task 2/4 ✓
- Python 3.12 镜像绕 host 3.14 + psycopg2 wheel 风险 → Task 1 ✓
- vault rsync 绕开 P2 → Task 2 ✓
- 迁移上生产库 + 备份 + 清空替换（用户决策）→ Task 3 ✓
- §决策8 长任务健壮性 → 容器 restart 策略（L2 常驻化 Phase 2 细化）

**阻塞 / 接线点（诚实标注）：**
- **P1 SSH** ✅ 已解（key 装好）。
- **P2 vault remote** → Phase 1 用 rsync 绕开，**不阻塞**；L1 服务化（append 回推）时才需。
- **P3 ③-C apply** → 首次 sync 只写 ②-B（relation_count 0）；③-C apply 后须先做 **CONTRACT-REL-1 对账**（BACKLOG B13）才有关系数据。
- **P-remote**：feat/service-deploy 当前是本地分支，服务器 clone 前需 push 上 github（先 rebase onto origin/main，见 handoff「分支衔接」）。
- **接线点（Plan A 补线，无新逻辑）**：`scripts/service/run_l2.py` CLI wrapper；L1 run_pipeline 写 l1_status + 防重叠守卫（L1 服务化时）。
- **前端团队协作**：迁移/清空替换动的是 safety-platform 生产库 + 数据 → 走 PR 给管理员（gloriahao0909），部署机制（他们的 compose/CI）需对齐。

**磁盘风险**：剩 4G。vault 144M + 镜像 ~250M + state 可控,但全盘 90% 已用,部署时盯 `df -h`。

**部署顺序**：Plan A 代码（含补线 run_l2.py 等）→ push 分支 → Plan B schema 迁移生成（PR）→ Plan C Task 2（vault+凭据）→ Task 3（备份+迁移+清空）→ Task 4（build+首次 sync）→ Task 5/6（L2 触发+验收）→ Plan B 端点/前端联调。
