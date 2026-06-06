# Plan C · 服务器部署 实施计划

> **For agentic workers / Codex:** 配套 spec：`docs/superpowers/specs/2026-06-06-service-deploy-design.md`。
> **⚠ 阻塞前置 P1：** SSH 登录服务器（8.216.59.173）当前密码认证被拒。**本计划在 SSH 打通前不能执行**——所有"上服务器后核实"的占位都因此。打通后先跑 Task 0 环境勘察，用实测值替换本计划中标 `<待核实>` 的项。
> **infra 计划的"测试"= 部署后可验证的运行态检查**（systemctl status / journalctl / curl），不是 TDD 单测。

**Goal:** 把 pipeline（Plan A）+ heng-guan（Plan B）部署到服务器，systemd 管理 L1（占位手动触发）/L2（L1 完成触发）/sync，凭据 out-of-git 安全注入，vault git 持久化。

**Architecture:** 两个 systemd unit（L1 占位 + L2 oneshot），L1 完成 ExecStartPost 触发 L2，L2 ExecStartPost 触发 sync。vault/pipeline git clone 到持久盘 `/data/`，凭据在 `/etc/policy-pipeline/models.env`(chmod 600)。

**Tech Stack:** systemd、bash、git、Python venv、PostgreSQL（heng-guan 既有 DB）。

---

## Task 0: SSH 打通后的环境勘察（必先做，替换占位）

> P1 解决后第一件事。把实测结果记进本计划，替换后续 `<待核实>`。

- [ ] **Step 1: 登录 + 基础环境**

```bash
ssh root@8.216.59.173 'cat /etc/os-release | head -3; python3 --version; df -h /; free -h; nproc'
```
记录：OS 发行版、Python 版本、磁盘可用、内存、核数。

- [ ] **Step 2: 网络连通性（两个境内端点）**

```bash
ssh root@8.216.59.173 '
  curl -s -o /dev/null -w "minimax:%{http_code}\n" --connect-timeout 5 https://api.minimaxi.com
  curl -s -o /dev/null -w "deepseek:%{http_code}\n" --connect-timeout 5 https://api.deepseek.com'
```
Expected: 两个都有响应码（非超时）。若超时 → 服务器地理位置/防火墙问题，记录并上报（影响模型调用，spec 决策 2 的境内端点前提）。

- [ ] **Step 3: heng-guan 部署现状 + PostgreSQL 位置**

```bash
ssh root@8.216.59.173 '
  docker ps 2>/dev/null | grep -i postgres
  which psql; systemctl is-active postgresql 2>/dev/null
  ls -la /data 2>/dev/null || echo "no /data"'
```
记录：PostgreSQL 跑在哪（docker / 系统服务）、连接方式、heng-guan 是否已部署、`/data` 是否存在/挂载。
**这决定 `DATABASE_URL` 和持久盘路径——是本计划最关键的未知。**

- [ ] **Step 4: 记录勘察结果**

把上述实测值填进本文件顶部"勘察结果"段（Codex 新建），替换全文 `<待核实>` 占位。

---

## Task 1: 持久盘目录 + git clone

**前置：** Task 0 完成，`/data` 持久盘确认（若无则 `<待核实>` 用实际持久路径）。

- [ ] **Step 1: 建目录骨架**

```bash
ssh root@8.216.59.173 '
  mkdir -p /data/vault /data/pipeline /data/pipeline/state
  mkdir -p /etc/policy-pipeline
  echo done'
```

- [ ] **Step 2: clone vault（前置 P2：vault 需有 GitHub remote）**

> **阻塞 P2：** vault 当前是否已有 GitHub remote 待用户确认。无则用户先建私有仓 push。
```bash
ssh root@8.216.59.173 '
  cd /data/vault && git clone <vault-git-remote> . && git log --oneline -1'
```
Expected: clone 成功，看到最新 commit（应含 ②-B 的 business_view 数据）。

- [ ] **Step 3: clone pipeline（feat/service-deploy 分支）**

```bash
ssh root@8.216.59.173 '
  cd /data/pipeline && git clone -b feat/service-deploy <pipeline-git-remote> repo
  cd repo && git log --oneline -1'
```
Expected: clone 成功，分支 feat/service-deploy。

- [ ] **Step 4: Python 环境**

```bash
ssh root@8.216.59.173 '
  cd /data/pipeline/repo && python3 -m venv .venv
  .venv/bin/pip install -e . && .venv/bin/python -c "import psycopg2, yaml, anthropic; print(\"deps ok\")"'
```
Expected: 打印 `deps ok`。

---

## Task 2: 凭据注入（out-of-git）

- [ ] **Step 1: 写 models.env（不经 git，手动 scp 或服务器上直接编辑）**

> 凭据**绝不进任何 git 仓**。从本地 `~/.config/policy-pipeline/models.env` 取值，加 `DATABASE_URL`。
```bash
# 本地：把现有 models.env 安全传上去（scp，不进仓）
scp ~/.config/policy-pipeline/models.env root@8.216.59.173:/etc/policy-pipeline/models.env
ssh root@8.216.59.173 'chmod 600 /etc/policy-pipeline/models.env'
```

- [ ] **Step 2: 追加 DATABASE_URL**

在服务器 `/etc/policy-pipeline/models.env` 末尾加（值用 Task 0 Step 3 实测的 PG 连接）：
```bash
# DATABASE_URL=postgres://<user>:<pass>@<host>:<port>/<heng_db>   ← <待核实>
```

- [ ] **Step 3: 验证可读 + 不在仓**

```bash
ssh root@8.216.59.173 '
  ls -la /etc/policy-pipeline/models.env   # 应是 -rw------- (600)
  cd /data/pipeline/repo && git check-ignore -v /etc/policy-pipeline/models.env 2>/dev/null || echo "outside repo (good)"'
```
Expected: 权限 600；文件在仓外。

- [ ] **Step 4: 冒烟 — sync 连 DB（只读连通性）**

```bash
ssh root@8.216.59.173 '
  set -a; . /etc/policy-pipeline/models.env; set +a
  cd /data/pipeline/repo
  .venv/bin/python -c "import os,psycopg2; c=psycopg2.connect(os.environ[\"DATABASE_URL\"]); print(\"db ok\"); c.close()"'
```
Expected: 打印 `db ok`。失败 → 检查 DATABASE_URL / PG 是否允许该来源连接（heng-guan schema 迁移需先由 Plan B 跑过）。

---

## Task 3: L2 + sync systemd unit（oneshot）

**Files（服务器）:**
- Create: `/etc/systemd/system/policy-pipeline-l2.service`

- [ ] **Step 1: 写 L2 service**

```ini
# /etc/systemd/system/policy-pipeline-l2.service
[Unit]
Description=Policy Pipeline L2 派生 + sync (oneshot, L1 完成后触发)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/data/pipeline/repo
EnvironmentFile=/etc/policy-pipeline/models.env
# L2 编排：消费 l2_queue → 归属增量 → [结晶/分析钩子] → 写账本 → 触发 sync
ExecStart=/data/pipeline/repo/.venv/bin/python -m scripts.service.run_l2 \
  --vault /data/vault \
  --state-dir /data/pipeline/state \
  --gen-model MiniMax-M2.7-highspeed --gen-provider anthropic \
  --judge-model deepseek-v4-flash --judge-provider openai
# 长任务健壮性（spec §决策8）
TimeoutStartSec=infinity
Restart=no
# journald 收日志：journalctl -u policy-pipeline-l2 -f

[Install]
WantedBy=multi-user.target
```

> **接线点（依赖 Plan A）:** `scripts.service.run_l2` 是 Plan A 编排器的 CLI 入口（Plan A Task 9 的 `orchestrate.drain_queue` 需配一个 `run_l2.py` CLI wrapper：读 models.env → 构造 `make_attribution_runner` + sync runner → `drain_queue`）。**若 Plan A 未含此 CLI wrapper，Codex 在 pipeline 仓补 `scripts/service/run_l2.py`**（薄封装，无新逻辑）。sync runner = 调 `scripts.sync.run_sync.run(...)`。

- [ ] **Step 2: reload + 手动跑一次验证**

```bash
ssh root@8.216.59.173 '
  systemctl daemon-reload
  # 先往队列塞一个测试 pid（或空队列直接跑确认不崩）
  systemctl start policy-pipeline-l2.service
  systemctl status policy-pipeline-l2.service --no-pager
  journalctl -u policy-pipeline-l2 -n 30 --no-pager'
```
Expected: service 跑完 status=inactive(dead) 且 result=success；journal 无 traceback。空队列时应优雅空转（编排器 `drain_queue` 空队列不触发 sync）。

- [ ] **Step 3: 验证 sync 真写了 DB（端到端，需 Plan B schema 已迁移）**

```bash
ssh root@8.216.59.173 '
  set -a; . /etc/policy-pipeline/models.env; set +a
  cd /data/pipeline/repo
  .venv/bin/python -m scripts.sync.run_sync --vault /data/vault --state-dir /data/pipeline/state --pipeline-version 1
  cat /data/pipeline/state/last_sync_run.json'
```
Expected: `last_sync_run.json` 显示 synced_count > 0（首次约 836 篇 ②-B 数据），errors 为空或可解释。DB 里 `SELECT count(*) FROM "Policy" WHERE "pipelinePid" IS NOT NULL;` 应非零。

---

## Task 4: L1 systemd unit（占位，不挂 timer）

**Files（服务器）:**
- Create: `/etc/systemd/system/policy-pipeline-l1.service`

> spec §8 TODO：L1 频率待定、采集方法待优化、SOP 需剥 L2 逻辑。本任务只建**占位 service**（手动触发），**不挂 timer**，等 L1 优化闭环后再配频率。

- [ ] **Step 1: 写 L1 service（占位）**

```ini
# /etc/systemd/system/policy-pipeline-l1.service
[Unit]
Description=Policy Pipeline L1 采集 (占位，手动触发；频率待 TODO 闭环)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/data/pipeline/repo
EnvironmentFile=/etc/policy-pipeline/models.env
# L1 启动写 l1_status: running；结束写 idle + new_pids；最后触发 L2
ExecStart=/data/pipeline/repo/.venv/bin/python -m scripts.l1_collect.run_pipeline \
  --vault /data/vault --state-dir /data/pipeline/state
# L1 完成后触发 L2 一次（spec §4.2：唯一触发=L1 完成事件）
ExecStartPost=/usr/bin/systemctl start policy-pipeline-l2.service
TimeoutStartSec=infinity
Restart=no

[Install]
WantedBy=multi-user.target
```

> **接线点:** `scripts.l1_collect.run_pipeline` 需支持 `--state-dir` 且在起止写 `l1_status.json`（用 Plan A 的 `scripts.service.l1_status`）。**若现有 run_pipeline 未写 l1_status，Codex 在 pipeline 仓补这层包裹**（启动 `set_running`、结束 `set_idle(pids_collected=new_pids)`）。L1 SOP 剥离 L2 逻辑是独立 TODO（spec §8），本任务不做。

- [ ] **Step 2: reload，确认不自动跑（无 timer）**

```bash
ssh root@8.216.59.173 '
  systemctl daemon-reload
  systemctl list-timers | grep policy-pipeline || echo "no l1 timer (expected)"'
```
Expected: 无 policy-pipeline timer（占位阶段不自动跑）。

- [ ] **Step 3: 防重叠确认（L1 不可并发）**

> 等 L1 频率确定时配死：cron/timer tick 先读 l1_status，running 跳过本次。
本任务记录约定，不配 timer。在 run_pipeline 入口加：若 `l1_status.is_running()` → 直接退出（exit 0，日志 "skip: L1 already running"）。
Run（验证逻辑存在）:
```bash
ssh root@8.216.59.173 'grep -rn "is_running\|already running" /data/pipeline/repo/scripts/l1_collect/ || echo "需 Codex 在 run_pipeline 加防重叠守卫"'
```

---

## Task 5: 部署验收 + 回滚预案

- [ ] **Step 1: 端到端验收清单**

```bash
ssh root@8.216.59.173 '
  echo "=== units ===" ; systemctl status policy-pipeline-l1 policy-pipeline-l2 --no-pager | grep -E "Loaded|Active"
  echo "=== state ===" ; ls -la /data/pipeline/state/
  echo "=== last sync ===" ; cat /data/pipeline/state/last_sync_run.json 2>/dev/null
  echo "=== creds 600 ===" ; stat -c "%a" /etc/policy-pipeline/models.env'
```
Expected: 两 unit loaded；state 目录有 last_sync_run.json；凭据 600。

- [ ] **Step 2: 前端能查到 pipeline 数据（联调 Plan B）**

heng-guan 政策列表/详情应能看到 `pipelinePid` 非空的政策。
```bash
curl -s localhost:3000/policies?pageSize=1 | grep -o pipelinePid || echo "需确认 list select 含 pipeline 字段"
```
Expected: 列表/详情返回含 pipeline 字段（Plan B Task 5 已扩展类型；后端 select 需含新字段——若 list 的 select 未含，Codex 在 policy.service list/findById 的 select 加 pipelinePid/importanceOverride/pipelineThemes）。

- [ ] **Step 3: 回滚预案（记录,不执行）**

```
回滚点：
- DB：Plan B 迁移可 `prisma migrate resolve --rolled-back` + 反向 SQL（新表 DROP，Policy 新列 DROP）。新字段都 nullable，不影响现有数据。
- systemd：systemctl stop + disable + rm unit + daemon-reload。
- vault/pipeline clone：直接删 /data 对应目录；vault 真值在 git remote，无损。
- 凭据：rm /etc/policy-pipeline/models.env。
关键：sync 只 upsert pipeline 字段，不动 heng-guan 原有 Policy 业务字段/外键 → 回滚不伤现有业务数据。
```

- [ ] **Step 4: 部署记录**

Create（服务器或 pipeline 仓 docs/）: 部署当天的实测值（OS/PG/路径/连通性）+ 验收截图，作为运维基线。

---

## Self-Review（对 spec 核对）

**Spec 覆盖：**
- §3 进程模型（L1/L2 systemd）→ Task 3/4 ✓
- §3 目录结构 + 凭据 EnvironmentFile → Task 1/2 ✓
- §4.2 L1 完成触发 L2 一次（ExecStartPost）→ Task 4 Step 1 ✓
- §4.4 L1 不重叠（oneshot 单例 + is_running 守卫）→ Task 4 Step 3 ✓
- §决策8 长任务健壮性（TimeoutStartSec=infinity，systemd 取代 caffeinate）→ Task 3/4 ✓
- §6 sync 端到端写 DB → Task 3 Step 3 ✓
- §8 L1 占位不挂 timer（频率 TODO）→ Task 4 ✓

**阻塞与接线点（必须诚实标注）：**
- **P1 SSH 未通** → 全计划阻塞，Task 0 先勘察替换占位。
- **P2 vault remote** → Task 1 Step 2 阻塞，待用户确认/建仓。
- **P3 ③-C apply** → 首次 sync 只写 ②-B 数据（spec §6），③-C apply 后自动追上，非阻塞。
- **接线点（Plan A 需补的薄 CLI）：** `scripts/service/run_l2.py`（编排 CLI wrapper）+ run_pipeline 写 l1_status + 防重叠守卫。三者都是薄封装、无新逻辑，Codex 落 Plan A 时一并补或在本计划补。
- **DATABASE_URL / PG 位置 / /data 持久盘** → Task 0 实测后替换 `<待核实>`，是最关键未知。

**部署顺序依赖：** Plan B 的 schema 迁移必须先于 Plan C Task 3 Step 3（sync 写 DB 需要表存在）。建议顺序：Plan A（代码）→ Plan B schema 迁移 → Plan C 部署 → Plan B 端点/前端联调。
