# Codex 交接 · 服务化部署本地实施（Phase 1 本地优先）

> 这份是给 Codex 的执行入口。**本地先实现 + 验证,服务器部署(Plan C)推迟到 SSH 通了再做。**
> 设计 spec 见 `docs/superpowers/specs/2026-06-06-service-deploy-design.md`。
> 三份计划:Plan A(pipeline)/ Plan B(heng-guan)/ Plan C(服务器,**本轮不做**)。

---

## 为什么本地优先

服务器 SSH(P1)和 vault 云仓(P2)只为**服务器部署**需要。本地开发**全绕开**:vault 已在 Mac 本地、pipeline 直接读、heng-guan 连本地 PostgreSQL。本地端到端验证通过后,Plan C 只是"把验证好的东西搬上服务器"。

---

## 本地环境(已核实)

| 项 | 值 |
|---|---|
| pipeline 仓 | `/Users/shaoziyuan/dev/政策分析-pipeline`,分支 `feat/service-deploy` |
| vault | `/Users/shaoziyuan/Documents/Zayn Main/政策分析`(本地直接读,**不需云仓**) |
| safety-platform 仓 | `/Users/shaoziyuan/Documents/战略大盘/safety-platform`(本地已 clone) |
| 本地 PostgreSQL | postgresql@15(homebrew),`localhost:5432`,superuser `shaoziyuan`,trust 无密码 |
| 工具链 | pnpm 10 / node 22 / psql 15 已装;**docker 不用**(走本地 psql,不用 `pnpm db:up`) |
| 模型凭据 | `~/.config/policy-pipeline/models.env`(gen=MiniMax-M2.7-highspeed / judge=deepseek-v4-flash) |

**DATABASE_URL(本地)**:`postgres://shaoziyuan@localhost:5432/heng_dev`

---

## 执行顺序

### 第 0 步 · 建本地库 ✅ 已完成(Claude 已建)

`heng_dev` 库已建好(`localhost:5432`,owner shaoziyuan)。PG15 内置 `gen_random_uuid()` 已验证可用,无需装 pgcrypto。Codex 跳过本步,直接从第 1 步开始。

```bash
# 已执行,无需重复:createdb -h localhost -U shaoziyuan heng_dev
```

### 第 1 步 · Plan A(pipeline 仓,Python)

在 `/Users/shaoziyuan/dev/政策分析-pipeline`(分支 `feat/service-deploy`)按
`docs/superpowers/plans/2026-06-06-service-deploy-plan-a-pipeline.md` 的 10 任务 TDD 实施。
**额外补 Plan C 接线点暴露的薄 CLI**(无新逻辑):
- `scripts/service/run_l2.py`:读 models.env → 构造 `make_attribution_runner` + sync runner → 调 `orchestrate.drain_queue` 的 CLI wrapper。
- L1 `run_pipeline` 加 `--state-dir` + 起止写 `l1_status`(set_running/set_idle)+ 入口 `is_running()` 防重叠守卫。

全程纪律:零真实 PID 字面量(`python3 -m scripts.audit.principle_guard scripts/service scripts/sync`)、TDD、`pytest -q` 全绿不碰坏现有 242+ 测试。

### 第 2 步 · Plan B 后端 schema 迁移(safety-platform 仓)

在 `/Users/shaoziyuan/Documents/战略大盘/safety-platform` 开 worktree/分支
`feature/heng-pipeline-integration`(**不推 master,最后 PR 给管理员**,附前端该懂描述+截图)。
先做 Plan B Task 1(Prisma schema 扩展 + 迁移),用本地 `heng_dev`:

```bash
cd services/heng-guan/backend
# .env 里 DATABASE_URL=postgres://shaoziyuan@localhost:5432/heng_dev
npx prisma migrate dev --name pipeline_integration
npx prisma generate
```
**关键校验**:迁移后 `pg_writer.py`(Plan A)的 quote 列名(`"pipelinePid"`/`"importanceOverride"`/`"PolicySemanticRelation"`)与 Prisma 生成的表/列**逐字一致**。

### 第 3 步 · 端到端验证桥(本地)

Plan A 代码 + Plan B schema 都就绪后,跑一次 sync 把 vault 数据推进本地 PG:
```bash
cd /Users/shaoziyuan/dev/政策分析-pipeline
set -a; . ~/.config/policy-pipeline/models.env; set +a
DATABASE_URL=postgres://shaoziyuan@localhost:5432/heng_dev \
  python3 -m scripts.sync.run_sync \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state-dir state/service --pipeline-version 1
cat state/service/last_sync_run.json
psql -h localhost -U shaoziyuan -d heng_dev \
  -c 'SELECT count(*) FROM "Policy" WHERE "pipelinePid" IS NOT NULL;'
```
Expected:synced_count 约 836;DB 查询非零。**这一步通=数据桥本地打通。**

### 第 4 步 · Plan B 端点 + 前端(safety-platform 仓)

按 Plan B Task 2-9 做端点 + Vue 页面。本地起:
```bash
cd services/heng-guan && pnpm install
pnpm dev:backend   # :3000
pnpm dev:frontend  # :5173
```
验证:政策列表/详情看到 pipeline 数据;手动录入走通(需 Task 9 poller 跑着);改分 + 恢复;L1 反馈池页渲染。

### 第 5 步 · 联调收口

- 改分后跑 sync,确认 `importanceOverride` 非空的政策 `importance` 不被踩(override 守卫)。
- 手动录入端到端:前端提交 → ManualEntryRequest 行 → poller 消费 → 状态推进。
- 收尾:pipeline 仓 commit(分支 feat/service-deploy);safety-platform 仓 PR 给管理员。

---

## 边界 / 不做

- **Plan C(服务器部署)本轮不做**——等 P1 SSH 通(晚上)。本地验证好后再搬。
- **③-C 语义关系**当前 preview 未 apply(P3)→ 首次 sync 只写 ②-B 的 business_view,relations 表暂空,apply 后下次 sync 自动追上。
- **分支衔接(2026-06-06 定)**:`feat/service-deploy` 与 origin/main **零文件重叠**(origin/main 阶段性 push 的 ③ 关系层落在 `scripts/analysis_relation_views/`,不碰 service/sync/pyproject/principle_guard/run_2b/SCHEMA 读路径)。**故不中途 rebase**——避免把 ~38 个 analysis_relation_views 测试灌进本线回归基线、搅乱每-task delta。各 task 在当前 base 跑完(回归基线 242→…→320 递增),**最终集成/PR 前再一次性 rebase onto origin/main**(无冲突)。
- **CONTRACT-REL-1(关系格式对账·延后)**:③ canonical 关系用 `from`/`to`/`rel`,本线 relation_mapper 吃 `from_pid`/`to_pid`/`relation_type`——③ 关系 apply 进 vault 时**必须对账**,否则 `PolicySemanticRelation` 表 0 行。详见 `docs/BACKLOG.md` B13。不影响当前进程(关系 sync 本就延后)。
- 分析/结晶增量、themeOverrides UI、L3 月报 = Phase 2。
- safety-platform 是另一条活跃线的仓,只在 `feature/heng-pipeline-integration` 动,PR 走管理员审,不直接推 master。

---

## 汇报要求(AGENTS.md)

每个阶段性任务收尾说明:在哪个大进程、本步完成什么、原则/门禁是否生效、建议下一步。有分叉给推荐路径。preview/机制说明不得被误认为正式产物。
