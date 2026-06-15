# pipeline 代码并入 safety-platform monorepo · 设计 spec

> 2026-06-15 · 公司决策:pipeline 代码搬入 safety-platform · brainstorming 产出 · 待用户复核 → Codex handoff(Codex 执行 / Claude 审收)
> 关联:S2 单生产者 `docs/runbooks/s2-vps-cron.md`、持续同步 S1 `docs/superpowers/specs/2026-06-08-stage1-continuous-sync-design.md`、service-deploy Plan B/C(DB 投影集成,已落地)。

## 背景与现状

三仓现状:

| 仓 | 位置 | 角色 |
|---|---|---|
| pipeline 工程仓 | `github.com/ZaynShao/policy-analysis-pipeline`(本仓) | 脚本 / SOP / 状态 / 文档 |
| vault 数据仓 | `github.com/ZaynShao/energy-policy-analysis` | raw markdown(2600 篇)+ 派生;276M(123M .git) |
| safety-platform | 公司 GitLab 主仓(+ GitHub 镜像) | monorepo,已全栈 Docker 部署在东京 VPS `/root/safety-platform`;`services/{heng-guan, guardian, guardian-backend, enterprise-kb, intel-center}` + root `docker-compose.yml` 编排 `platform-net` |

已有集成(6/6–6/7 Plan B/C,已落地在跑):pipeline 作为独立容器挂 external `safety-platform_platform-net`,`run_sync` 把 vault 投影进 `heng-pg`。**数据早已流入平台;代码与原始数据仍住各自仓。** 本次只解决"代码住哪"。

## 决策(已与用户敲定)

1. **驱动 = 统一代码库**:pipeline 源码作为 `services/policy-pipeline/` 进 monorepo,同一 MR + CI 流。
2. **vault = 独立数据仓,不进 monorepo**;只读消费;git 同步不变。
3. **搬码方式 = 干净拷贝 + 旧仓归档**(不带 git 史进公司仓)。
4. **文档迁移 = 只带运维文档**(SCHEMA/OPERATIONS/runbooks/README);内部工作笔记(handoffs/superpowers/BACKLOG/LESSONS/CHANGELOG)留旧仓。
5. **权限** = 用户已有 safety-platform 写/MR 权限,可直推或开 MR。

## Goal

把 pipeline 当前 `main` HEAD 的**代码**干净落入 `safety-platform/services/policy-pipeline/`,VPS 部署改从该子目录 build,旧仓归档;**vault 同步与 heng-pg 投影零回归**。

成功标准:

1. monorepo MR 合并,GitLab CI 过(pipeline `tests/` 绿)。
2. VPS 从 monorepo 子目录成功 build pipeline 容器。
3. 一次端到端 cron tick 跑通:L1 增量 → L2 派生 → vault push → `run_sync` 投影 → heng-guan 见数据。
4. vault 同步无回归(VPS push / Mac pull / Obsidian 见最新)。
5. heng-pg 行数对账无掉(搬前 / 搬后 policies + relations 计数一致)。

## 非目标(明确不做,留后续独立决策)

- **统一部署**:不把 `policy-pipeline` 折进 root `docker-compose.yml`;保留独立 service compose 挂 external net。(用户未选)
- **vault 所有权迁移**:vault 仓维持 `ZaynShao/energy-policy-analysis`;只读消费经 heng-pg 投影。未来可独立做(见 §3 同步变体)。(用户未选)
- **SCHEMA 升格 `contracts/`**:可选,本次不做。
- **vault 原始数据入 monorepo**:明确不做(避免 270M 数据 + 史撞胖公司仓拖慢全团队 clone/CI)。

## Architecture(目标形态)

```
safety-platform (公司 monorepo · GitLab 主 + GitHub 镜像)
├── services/
│   ├── heng-guan/                ← 现有(前端消费 heng-pg)
│   ├── guardian/ kb/ intel-center/
│   └── policy-pipeline/          ← 【新】pipeline 整体落这里(干净拷贝)
│       ├── scripts/ tests/ Dockerfile constraints.txt pyproject.toml
│       ├── docker-compose.server.yml (build context 随之进子目录)
│       ├── SCHEMA.md OPERATIONS.md README.md docs/runbooks/
│       ├── AGENTS.md(服务级精简版,monorepo 级规则归 root)
│       └── (state/ 仅 git-tracked channel_catalog;运行时 state 不进仓)
└── contracts/                    ← (可选 / 非目标)SCHEMA 升格为正式契约

energy-policy-analysis (vault · 独立数据仓 · 不进 monorepo · 维持现状)
   └── git = 同步总线:VPS 单生产者 push → 所有人 pull(只读)
```

三条线改动量:

| 线 | 现状 | 搬后 | 改动量 |
|---|---|---|---|
| 代码 | 独立仓 `ZaynShao/policy-analysis-pipeline` | `safety-platform/services/policy-pipeline/` | **大**(本次主体) |
| vault 数据 | 独立 git 仓,VPS push / 各端 pull | **不变** | 无 |
| VPS 部署 | `/root/policy-pipeline-src` = clone pipeline 仓 | 从 monorepo 子目录 build | **小**(改源路径 + 卷路径) |

## Components / 工作分解

### 1. 代码落仓(`services/policy-pipeline/`)

**带进去**:`scripts/` `tests/` `Dockerfile` `.dockerignore` `constraints.txt` `pyproject.toml` `docker-compose.server.yml` + `SCHEMA.md` `OPERATIONS.md` `README.md` `docs/runbooks/` + 服务级 `AGENTS.md`(精简版,指向运维文档;monorepo 级规则归 root)+ `state/` 内 **git-tracked 的** `channel_catalog`(其余 state 运行时产物不进)。

**不带**:`.git/`(干净拷贝,无史)、`state/` 运行时产物、`docs/handoffs/` `docs/superpowers/` `docs/BACKLOG.md`(内部工作笔记)、`LESSONS.md` `CHANGELOG.md`(偏内部沉淀)、`CLAUDE.md`(本仓反污染纪律,服务级用精简 AGENTS.md 替)、`.claude/` `.pytest_cache/` `.superpowers/`。

要点:
- 路径 / 凭据已全 env/CLI 化(零硬编码),搬后无需改源码硬编码路径。**核对** compose net `safety-platform_platform-net`(external,不变)。
- 开 MR → GitLab CI 加 pipeline 专属 pytest job(用其自身 pip + constraints,**不与 root uv.lock 纠缠**,服务自包含独立 Dockerfile)→ 与平台 `.gitlab-ci.yml` 协调 → 合。

### 2. VPS 部署改源路径

现状(`docs/runbooks/s2-vps-cron.md`):`/root/policy-pipeline-src` = clone pipeline 仓 main;`docker compose -f docker-compose.server.yml build`;所有 cron 行 `cd /root/policy-pipeline-src && docker compose ...`。

改为从 `/root/safety-platform/services/policy-pipeline/` build(**平台团队已 clone monorepo 在机器上,复用,不另发 GitLab key**)。保留独立 service compose 挂 external net(非目标 = 不折进 root compose)。

**三处具体改动(handoff 给 Codex 逐条):**

1. **cron 行 cwd**:所有 `cd /root/policy-pipeline-src` → `cd /root/safety-platform/services/policy-pipeline`(compose `build: .` 是相对其所在目录,随服务进子目录后不变)。
2. **⚠️ 卷路径(易漏)**:`docker-compose.server.yml` 中 `policy-producer` 的 `/root/policy-pipeline-src/state:/app/state`(挂的是 **git-tracked `channel_catalog`**)→ 必须改成新 checkout 的 `/root/safety-platform/services/policy-pipeline/state`。漏改 = channel_catalog 读到旧路径,渠道目录失效。
3. **代码更新流程**:`cd /root/safety-platform && git pull && docker compose -f services/policy-pipeline/docker-compose.server.yml build`(或等价);flock 路径 `/var/lock/policy-pipeline-producer.lock`、log 路径 `/var/log/policy-pipeline/` 不变。

`/root/policy-pipeline-src` 保留作回滚锚,cutover 稳定后再清。
预存 wart(非本次):compose 默认 `command` 仍引 `MiniMax-...`/anthropic(已弃,cron 已 override),不动。

### 3. vault 同步(明确:不变)

vault 同步走 **vault 仓自己的 git 链路**,与代码住哪个仓**解耦**。三脚本逻辑一行不改,只随 checkout 位置移动:

- `produce_and_push`(`github-vault-rw` 写 key,push GitHub vault 仓)
- `sync_tick`(21:00 拉回外部变更 + 防误删守卫)
- `run_sync`(读本地 `/root/policy-vault` → upsert heng-pg)

**凭据双平面**:代码 pull = GitLab read(复用平台已有 monorepo clone);vault push = GitHub 写 key **不变**。

**维护点**:① history 增长(bot 每天多条机器 commit,.git 123M 持续涨)→ 消费方一律 `git clone --depth=1` 浅克隆;跨阈值再议 squash(慎,会断现存 clone)。② SCHEMA 镜像一致 → canonical 在 service,vault 留副本,runtime 同机锁步天然一致;改 SCHEMA 走 MR 时同步 vault 镜像。

**同步变体(未来可选,不阻塞本次)**:若 vault 也要归公司,迁到公司 GitLab group → **只换两件**:`produce_and_push` 的 remote URL + 换 GitLab 写 key。同步拓扑 / flock / sync_tick 全不变。低风险、可逆、可独立做。

### 4. 旧仓归档

`ZaynShao/policy-analysis-pipeline` → GitHub archived / 只读;README 顶部加指针:"代码已迁 `safety-platform/services/policy-pipeline/`,本仓为历史归档 + 工作笔记(handoffs/specs/plans/BACKLOG/LESSONS)存档。" 工作笔记留此仓,不丢、不污染公司仓。

## Data flow(搬后一次 cron tick,验证无回归)

1. (代码已在 monorepo 子目录 build 成 `policy-pipeline:latest` 镜像)
2. cron 行 cd 新子目录 → 容器跑 L1 增量 → 写 `/vault` → `produce_and_push` 推 GitHub vault 仓。
3. L2 派生 → `produce_and_push` 推(各 whitelist 分段)。
4. 10:00 投影:`run_sync` 读本地 vault → upsert heng-pg(持 producer flock,不读半成品)。
5. heng-guan UI 见新数据;Mac `git pull` 见最新。

## Testing / 验收

**MR 侧**:GitLab CI pipeline pytest job 绿(现有 `tests/` 跑通)。

**部署侧(监督首跑,人在场;对照 `s2-vps-cron.md` §2):**

1. VPS 新子目录 `docker compose build` 成功 → `docker run --rm policy-pipeline:latest python -c "import trafilatura, bs4"` 过。
2. 手跑一条 cron 等价命令(如 07:30 评论 ingest,持 flock)→ vault commit+push 成功 → GitHub `origin/main` 同 HEAD,`git -C /root/policy-vault status` 干净。
3. 手跑 10:00 投影命令 → `/root/policy-pipeline-state/last_sync_run.json` `errors=[]`。
4. **heng-pg 行数对账**:搬前记录 policies + relations 计数;搬后首投影后比对,无掉。
5. 飞书无告警(健康 = 静默)。

**回滚**:cron 源路径 + 卷路径切回 `/root/policy-pipeline-src`(回滚锚保留期内),一次性、原子。

## Risks / 约束

- **GitLab CI 对齐**:pipeline 用 pip + constraints(非 monorepo uv);服务自包含,运行时不与 root uv.lock 纠缠;CI 给独立 job 用其自身依赖。需与平台 `.gitlab-ci.yml` 协调(handoff 列为待平台确认项)。
- **工作流改变**:pipeline 改动以后走公司 GitLab MR 流(不再 GitHub PR);Claude 审 diff 仍适用,落地走 MR。
- **凭据**:VPS 代码 pull 用 GitLab read(大概率复用平台已有 monorepo clone);vault GitHub 写 key 不变;**凭据绝不入 git / 不打印**(server-ops 红线)。
- **double-checkout 窗口**:cutover 期 `/root/policy-pipeline-src`(旧)与 monorepo 子目录(新)并存;cron 只能指一处,切换必须原子(改 crontab 一次性切 + 验证 + 回滚锚)。
- **flock 共享**:写 vault 的行仍共持 `/var/lock/policy-pipeline-producer.lock`;搬后 cron 行 cwd 变但锁路径不变,**确认所有行同锁**。
- **卷路径漏改**:§2 改动 2 的 `/app/state`(channel_catalog)是最易漏点,漏改静默失效渠道目录 → 验收必查 `ls .../services/policy-pipeline/state/T1_channels/channel_catalog.yaml` 容器内可见。

## 落地物

- monorepo:`services/policy-pipeline/`(代码 + 运维文档 + 服务级 AGENTS.md)+ MR + CI job。
- VPS:cron 源路径 + 卷路径切换、代码更新流程、回滚锚。
- 旧仓:archived + README 指针。
- 本仓:`OPERATIONS.md` 补"搬入 monorepo 后的部署 / 更新 / 回滚"节;本 spec;Codex handoff(`docs/handoffs/`)。

## 分工(`codex-division-of-labor`)

- **Claude**:本 spec + Codex handoff + 审收 MR diff + 审收 VPS cutover。
- **Codex**:执行(开 MR、CI job、VPS cron + 卷路径切换、归档旧仓)。
- **用户亲手**:凭据 / 生产写 / VPS 部署 harness(server-ops 红线)。
