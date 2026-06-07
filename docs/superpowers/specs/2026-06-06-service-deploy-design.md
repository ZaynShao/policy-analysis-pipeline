---
title: 政策分析服务化部署设计(Service Deploy)
status: spec v1（待用户复核 → writing-plans）
date: 2026-06-06
branch: feat/service-deploy
authors: Claude（设计/评估/审计）+ Codex（实施）
related:
  - docs/2026-05-30-top-level-design-v2.html（顶层设计 charter）
  - SCHEMA.md（vault 数据契约）
  - 前端仓 github.com/gloriahao0909/safety-platform（services/heng-guan）
---

# 政策分析服务化部署设计

> 把已建成的 L1 采集 + L2 加工 pipeline 部署到服务器(8.216.59.173)，
> 变成 **定期抓 → 定期派生 → 前端主动消费** 的正式服务。
>
> 本 spec 只覆盖 Phase 1。结晶前端视图、主题人工覆盖 UI、L3 月报等留 Phase 2（见 §9）。

---

## 0. 命名纪律(沿用项目既定约定)

三层外壳只用名字：**采(L1) → 加工(L2) → 取(L3)**。L2 内部阶段也用名字：**源 · 归属 · 分析 · 结晶**。
代码里历史沿用的 ②-A/②-B/③-B/③-C 只是这些阶段下的子任务代号，不是层。

- **采(L1)** = 八步采集法，append-only 抓取、去重。入口 `scripts/l1_collect/run_pipeline.py`。
  产出 = **源**：冻结的政策真值(vault `0_raw/`)，是采(L1)与加工(L2)的接缝。
  ⚠ "源"是采的产出、不是加工的内脏；"采完没"和"加工建没建好"是两件事。
- **加工(L2)** = 归属 + 分析 + 结晶，幂等命令、temp0、整文件重生、不打补丁。
- **取(L3)** = 消费：本次只做"给前端供数据"，不做生成式产物。

派生依赖链：采 → 冻结源 → 归属(确定性身份→主题打分) → 分析(确定性关系→语义关系) → [结晶] → 取。

---

## 1. 整体拓扑与数据流

```
本地 Mac (开发)                服务器 8.216.59.173
─────────────────────          ──────────────────────────────────────────────
                               /data/vault/          ← vault git 仓(持久盘)
                               /data/pipeline/state/ ← hash ledger + 运行产物
                               /etc/policy-pipeline/models.env ← 凭据(chmod 600)

                               ┌──── Python pipeline worker (systemd) ────┐
                               │  [L1 cron, 频率TBD] ──→ vault 0_raw/     │
                               │       ↓ 写 last_l1_run.json + l1_status   │
                               │  [L2 trigger, 唯一触发=L1完成]            │
                               │    归属(②-B) ──→ state/ + vault biz_view│
                               │    分析(③-C) ──→ state/ + vault relations│
                               │    结晶      ──→ state/ themes/(纯计算)   │
                               │       ↓                                   │
                               │  [sync] ──→ PostgreSQL upsert             │
                               └────────────────────────────────────────────┘
                                              │ 直连(psycopg2)
                               ┌──── PostgreSQL (heng-guan DB) ───────────┐
                               │  Policy(+pipelinePid 等新字段)            │
                               │  PolicySemanticRelation [新]              │
                               │  ManualEntryRequest [新]                  │
                               │  L1FeedbackQueue [新]                     │
                               └────────────────────────────────────────────┘
                                              ▲
                               ┌──── heng-guan NestJS + Vue 3 ────────────┐
                               │  /api/policy/*            列表/详情/关系  │
                               │  /api/policy/manual-entry 手动录入        │
                               │  /api/policy/:id/override-importance 改分 │
                               │  /api/feedback/*          L1 改进池       │
                               └────────────────────────────────────────────┘
git push/pull ◄────────────── vault git remote (GitHub) ◄── 服务器每日 push
```

**两个关键接缝**：
- `pipeline ↔ vault`：通过 SCHEMA.md 契约（现有）。
- `pipeline ↔ heng-guan DB`：通过 Prisma schema 扩展契约（新建，见 §5 字段映射表）。
  这是项目"两仓通过契约解耦"模式的第三次延伸，同 vault↔pipeline 的解耦逻辑。

---

## 2. 架构方案选型（已定）

**方案 B：Pipeline 独立仓 + sync 层直连 PostgreSQL。**

- Pipeline 留在 `~/dev/政策分析-pipeline/`，自有 git 历史、AGENTS/LESSONS 纪律完整。
- 在 pipeline 仓新增 `scripts/sync/`，L2 跑完后连 heng-guan PostgreSQL upsert 派生产物。
- heng-guan Prisma schema 的扩展走 safety-platform 仓 PR（附截图+前端该懂的描述）。

否决的备选：
- 方案 A（pipeline 并入 safety-platform 仓）：两套语言/规范混住，迁仓代价大。
- 方案 C（sync 走 heng-guan 内部 API）：多一个端点+重试队列，调试链路更长，比直连脆。

两仓变更边界：
```
政策分析-pipeline (Python)          safety-platform (Node/Vue)
────────────────────────────────    ────────────────────────────
scripts/sync/ 新增                  services/heng-guan/backend/
  → 连接 PostgreSQL                   prisma/schema.prisma 扩展
  → upsert pipeline 产物              → 新字段/新表 + NestJS 端点 + Vue 页面
                    共同约定：DB schema 字段映射表（§5）
```

---

## 3. 服务器进程与目录结构

**进程模型** —— 两个独立 systemd service，不互相依赖启动：

```
policy-pipeline-l1.service    ← L1 采集（初期手动触发，不挂 timer，待频率 TODO 闭环）
policy-pipeline-l2.service    ← oneshot，L1 完成后 ExecStartPost 触发，跑完自动 stop
```

- L1 完成写 `last_l1_run.json` + `l1_status: idle` → 触发 L2 service start 一次。
- L2 结束写 `last_l2_run.json`。
- 所有 stdout/stderr 走 journald；`journalctl -u policy-pipeline-l2 -f` 实时看日志。
- L2 service 设 `Restart=on-failure`、`TimeoutStartSec=infinity`。
- Linux 不需要 `caffeinate`；systemd 取代本地的 `nohup caffeinate`。

**目录结构**：

```
/data/
├── vault/                    ← git clone 政策分析 vault
│   ├── 0_raw/
│   ├── _meta/business_view/
│   └── 1_extracted/relations/
└── pipeline/
    ├── repo/                 ← git clone 政策分析-pipeline (feat/service-deploy → main)
    └── state/                ← 不进 git
        ├── hash_ledger.json
        ├── l1_status.json
        ├── l2_queue.jsonl
        ├── last_l1_run.json
        ├── last_l2_run.json
        ├── last_sync_run.json
        ├── node2b/
        └── node3c/

/etc/policy-pipeline/
└── models.env               ← chmod 600, root only
    # ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY  (MiniMax gen)
    # OPENAI_BASE_URL / OPENAI_API_KEY         (deepseek judge)
    # DEEPSEEK_MODEL
    # DATABASE_URL                              (heng-guan PostgreSQL)
```

**调用约定**：

```bash
python3 -m scripts.l1_collect.run_pipeline \
  --vault /data/vault --state-dir /data/pipeline/state
```

L2 当前不是单一入口，而是分阶段模块（归属 `scripts.l2_themescore.run_2b`、
分析 `scripts.analysis_semantic_relations.run`、结晶待确认）。服务化需要一个
**L2 编排入口**串起：归属 → 分析 → 结晶 → sync，并接增量队列。

> **接线点（Codex 落地时确认）**：是新建 `scripts/l2_orchestrate/run.py` 编排
> 现有阶段模块，还是扩展某个现有 run。本 spec 约定的是编排"行为契约"
> （读队列 → 按 pid 整文件重生各阶段 → 写 ledger → 触发 sync），不约定具体模块名。
> 各阶段模块本身已存在且测试齐全，不重写，只被编排调用。

---

## 4. 增量策略、L2 触发、队列与并发控制

### 4.1 增量派生（content-hash ledger）

`state/hash_ledger.json`：每个 pid 存 `raw_content_hash` + `pipeline_version`。
派生前比对：
- hash 未变 且 pipeline_version 未变 → 跳过，用缓存结果。
- hash 变了 / 新 pid / pipeline_version bump → 重跑。

成本：每日只跑新增政策，存量接近零成本。
- 主题打分(②-B)：~2 pass/篇 MiniMax。
- 语义关系(③-C)：候选对 deepseek 判定。
- 结晶：0 LLM（纯计算）。

`pipeline_version`：重大代码变更（换 prompt/换模型/改评分逻辑）bump → 触发全量重跑；
小修不 bump，接受存量是旧版本、增量拿新版本。与"整文件重生"纪律一致。

### 4.2 L2 触发：一次任务，不反复触发

触发信号是 **"L1 完成事件"**，不是"每篇政策入库事件"。

```
L1 启动 → 写 l1_status: running
  ├─ 政策陆续入库 0_raw/   ← 不触发 L2
  └─ 政策 N 入库            ← 不触发 L2
L1 结束 → 写 last_l1_run.json {new_pids:[...]} → l1_status: idle
        → ExecStartPost 触发 L2 一次（唯一触发点）
              ↓ L2 把整批 new_pids 写进 l2_queue（priority: normal）
```

无论 L1 这轮抓进来多少篇，L2 只被唤醒一次，拿到整批 new_pids。

### 4.3 单 worker + 显式队列

L2 是有状态串行长任务（受 API 并发限制）。手动录入与 cron 触发共用一个队列、一个 worker：

```
手动录入(high) ─┐
                ├─→ l2_queue.jsonl ─→ 单一 L2 worker（串行消费）
cron 触发(normal)┘
```

- `l2_queue.jsonl` 持久化：`{pid, trigger:manual|cron, priority:high|normal, requested_at}`。
- worker 单进程，优先取 high 条目（手动插队）。
- 防 race：单 worker 串行写 hash_ledger / vault，无并发写冲突；无多进程打 API → 无 429。

### 4.4 L1 run 不重叠

systemd oneshot 天然单例；cron tick 时先读 `l1_status`，running 就跳过本次。
等 L1 频率确定（§8 TODO）一起配死。现在 L1 不挂 timer，不触发。

---

## 5. heng-guan Schema 扩展（Route C）+ 字段映射契约

> 用户决策：以高精度 pipeline 数据为权威，前端模型迁就 pipeline，不是反过来。
> 这一节是 pipeline↔DB 的契约。pipeline `scripts/sync/` 按此写 SQL；
> heng-guan Prisma 按此扩展。任一侧改动需同步本节并走 PR。

### 5.1 Policy 模型新增字段

```prisma
model Policy {
  // 现有字段全部不动（CUID 主键、外键关联保留）

  // Pipeline 身份（业务键 + 代理键模式）
  pipelinePid     String?   @unique   // P_2024_NDRC_718；null = 手动录入
  pipelineVersion Int?

  // Pipeline 派生（sync 步写入）
  pipelineScores  Json?     // {D1..D6, importance, value_tags}
  pipelineThemes  Json?     // [{id,label,score,isPrimary,isComprehensive}]
  pipelineImpact  String?   // ②-B impact_analysis
  syncedAt        DateTime?

  // 人工覆盖
  importanceOverride PolicyImportance?  // 非 null 时前端显示覆盖值
  themeOverrides     Json?              // Phase 2 UI

  // 关联
  semanticRelations   PolicySemanticRelation[] @relation("SemFrom")
  semanticRelatedFrom PolicySemanticRelation[] @relation("SemTo")
  manualRequests      ManualEntryRequest[]
}
```

风险1 处置（已评估为代码健康）：保留 CUID 不动，加 `pipelinePid` 业务键。
现有 Visit/Briefing/Monthly 外键不迁移。前端展示用 pipelinePid，DB 内部关联用 CUID。

### 5.2 三张新表

```prisma
model PolicySemanticRelation {
  id            String  @id @default(cuid())
  fromPolicyId  String
  toPolicyId    String
  relationType  String  // derives_from/extends/iterates/aligns_with/cites_basis/
                        // references/clarifies/supersedes/conflicts_with（9 类）
  confidence    Float?
  evidence      String?
  pipelineVersion Int?
  fromPolicy    Policy  @relation("SemFrom", fields:[fromPolicyId], references:[id])
  toPolicy      Policy  @relation("SemTo",   fields:[toPolicyId],  references:[id])
  createdAt     DateTime @default(now())
  @@unique([fromPolicyId, toPolicyId, relationType])
}

model ManualEntryRequest {
  id             String   @id @default(cuid())
  submittedUrl   String
  submittedBy    String
  status         String   @default("checking")
  // checking / already_exists / l1_running_queued / processing /
  // completed / feedback_created
  resultPolicyId String?
  feedbackId     String?
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
}

model L1FeedbackQueue {
  id              String   @id @default(cuid())
  reportedUrl     String
  reportedTitle   String?
  reportedBy      String
  expectedChannel String?
  l1ScanDate      DateTime?
  status          String   @default("pending")  // pending / reviewed / resolved
  reviewNote      String?
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt
}
```

### 5.3 现有表处置

| 表 | 处置 |
|---|---|
| `AnalysisTopic` / `ImportanceRule` | 停止 auto-derivation；保留为可选人工配置（前端可查看，不再驱动打分）。迁移脚本留 Phase 2。 |
| `PolicyRelation`(4 类) | 保留用于手动建关系；与 `PolicySemanticRelation`（pipeline 自动产）并存。 |
| `Policy.aiKeyPoints / aiImpactAnalysis` | 保留。这是 NestJS 按需 AI 解读（用户点按钮才生成），与 `pipelineImpact` 是两件事。 |

### 5.4 sync 字段映射表

| vault 来源 | DB 目标 | 规则 |
|---|---|---|
| `_meta/business_view/{pid}.yaml` → pid | `Policy.pipelinePid` | 唯一键，冲突 UPDATE |
| `scores.importance` | `Policy.importance` | **仅当 `importanceOverride IS NULL` 时覆盖** |
| `themes[]` | `Policy.pipelineThemes` (JSON) | 整体替换 |
| `scores` | `Policy.pipelineScores` (JSON) | 整体替换 |
| `impact_analysis` | `Policy.pipelineImpact` | 整体替换 |
| `1_extracted/relations/*.jsonl` | `PolicySemanticRelation` | UPSERT by (fromPid,toPid,relationType) |

---

## 6. Sync 层（pipeline → PostgreSQL）

```
scripts/sync/
├── run_sync.py        ← 入口，L2 ExecStartPost 触发
├── policy_mapper.py   ← vault YAML → Prisma Policy 字段
├── relation_mapper.py ← vault relations JSONL → PolicySemanticRelation
└── pg_writer.py       ← psycopg2 raw SQL，INSERT ... ON CONFLICT DO UPDATE
```

不引入 ORM。Prisma schema 归 heng-guan 所有，pipeline 只写 SQL，接缝靠 §5 契约维护。

**核心约束**：
- 只 upsert，不删除；sync 不碰 `pipelinePid IS NULL` 的手动录入记录。
- `importanceOverride` 有值时不覆盖 `importance`——人工改分不被 pipeline 重跑踩掉。
- sync 完成写 `state/last_sync_run.json` `{synced_count, skipped_override_count, errors[]}`。
- `DATABASE_URL` 从 `/etc/policy-pipeline/models.env` 读。

**首次部署限制（诚实披露）**：③-C 语义关系当前在 preview 阶段，vault `1_extracted/relations/`
还没有新数据；首次 sync 只写 ②-B 的 836 篇政策数据。③-C apply 完成后下次 sync 自动追上。

---

## 7. 手动录入流 + L1 漏采反馈 + 改分

### 7.1 手动录入：落 L1 收尾，触发 L2

落 **L1 收尾**（不是前置）：跳过发现/扫描(Step 1-3)，从抓取+入库(Step 4-5)进入，
正常入库后自动触发这一篇的 L2。数据质量路径与自动采集一致，只是"发现"被人工替代。

```
用户提交 URL
     ↓ 读 l1_status.json
     ├─ status == running
     │     → 进"待复核队列"，返回前端"采集任务进行中，稍后自动确认"
     └─ status == idle
           → 查 vault 0_raw/（权威源，非 DB——DB 可能落后几分钟）
                ├─ 找到 → 返回"已存在，这是它"
                └─ 找不到 → 进 L1 Step4 + L2 队列（high 优先级）

L1 完成（status → idle）：
     → 扫"待复核队列"，对每条重跑 vault dedup
          ├─ L1 已采到 → 通知"系统刚抓到，无需手动录入"
          └─ L1 未采到 → 自动触发该条 L1 Step4 + L2

L2 已扫过该来源但没抓到该篇 → 记 L1 漏采反馈：
     { reportedUrl, reportedTitle, expectedChannel, l1ScanDate, reportedBy }
     → 进 L1FeedbackQueue（status: pending），不影响主路径
```

两条纪律：
1. **dedup 查 vault，不查 DB**（vault 是真值，DB 是派生可落后）。
2. **l1_status 是唯一 L1 运行信号**，不用进程存活判断。

### 7.2 NestJS 端点 + 状态机

`POST /api/policy/manual-entry` → 轮询 `GET /api/policy/manual-entry/:id/status`（每 5s，完成停）。
状态：checking / already_exists / l1_running_queued / processing / completed / feedback_created。

### 7.3 L1 改进池页面（新）

给 GA 管理员的内部页：列 `L1FeedbackQueue`，展示 URL/标题/上报人/时间/预期渠道，
操作：标记 reviewed/resolved + 填 reviewNote。核心价值：给 L1 优化提供数据输入
（哪个渠道反复出现 → 优先排进 L1 TODO 闭环）。

### 7.4 人工改分

政策详情页"覆盖重要性"（限 HQ_GA / MANAGER）：
`PATCH /api/policy/:id/override-importance { importance }`
- 写 `Policy.importanceOverride`；前端有覆盖值则显示覆盖 + "人工标注"角标。
- sync 重跑跳过有 override 的 importance 字段（§5.4）。
- 传 null 撤销，恢复 pipeline 值。
- 主题覆盖（themeOverrides）留 Phase 2。

---

## 8. 部署前置条件 + TODO

### 8.1 部署前必须完成的前置项

| # | 事项 | 卡点 | 负责方 |
|---|---|---|---|
| P1 | SSH 登录服务器打通 | ✅ **已解（2026-06-07）** key 装好，root 免密 | — |
| P2 | vault 上服务器 | ✅ **Phase 1 用 rsync 绕开**（不需 GitHub remote）；L1 服务化（append 回推）时才需 remote | — |
| P3 | ③-C preview → apply（语义关系进 vault） | Task10 preview 跑完后 apply；**apply 后须先做 CONTRACT-REL-1 对账（BACKLOG B13）** | pipeline 工作流 |

> **⚡ 服务器实测 + 决策（2026-06-07，重写 Plan C v2 容器版）**：实测发现 **heng-guan 全栈已 Docker Compose 部署在服务器并在跑**（heng-pg=容器 `platform-heng-pg`/pgvector pg15，网络 `safety-platform_platform-net`，DB `hengguan`/user `heng`，5432 不暴露 host；真 schema 在 `/root/safety-platform/.../prisma/schema.prisma`）。host Python 3.14（psycopg2 wheel 风险）。**决策**：① pipeline 做成 **Docker 容器挂 platform-net**（镜像钉 py3.12，服务名 `heng-pg:5432` 连库）；② Prisma 迁移打**线上生产库**（迁移前 `pg_dump` 备份）；③ 生产现有 **50 条演示 Policy → 清空替换**（TRUNCATE CASCADE，pipeline 成唯一权威=Route C；用户已拍，PR 时前端团队会看到）；④ 新 Policy id 用 **UUID**（`gen_random_uuid()`，内部代理键、前端展示走 pipelinePid，可逆）。详见 Plan C v2 + memory `service-deploy-2026-06-06`。契约对账（对真生产 schema）已过：enum PolicyImportance + importance 列已存在且与 `importance_to_enum` 一致、零 @map。

### 8.2 TODO（必须主动闭环，不随服务化静默掉）

> **[L1 服务化前置]** L1"抓"的 cron 频率待定、采集方法待优化、L1 SOP 需剥离
> 混入的 L2 加工逻辑（旧版 SOP 的 Step4.5/5C/6.5/7/8 剥到 L2）。
> 当前 L1 service 部署为占位（手动触发，不挂 timer），L2 路径先跑通。
> **触发时机**：③-C 稳定后专门起 L1 优化 session。
> **状态**：L2 重建已近完成，L1 优化未启动——这是真实进度断层，需显式闭环。

---

## 9. 边界外（Phase 2 = 第一轮上线验收后再开新一轮设计/开发）

Phase 2 不是"以后随手加"，而是 Phase 1 稳定验收后**显式开启下一轮 brainstorm+spec+plan**。
触发时机：Phase 1 上线 + ③-C apply 进 DB + L1 TODO 闭环后。

- 结晶的前端展示（主题聚类视图、关系图谱可视化）
- 主题人工覆盖（themeOverrides）UI
- `AnalysisTopic` / `ImportanceRule` 迁移/清理脚本
- L3 月报 / 深度期刊（生成式产物，"取得专业"需呈现规范集，形态未定）

---

## 10. 实施分工

| 动作 | 谁做 |
|---|---|
| 设计、评估、审计、PR review | Claude（本 session） |
| pipeline 代码（`scripts/sync/`、L2 队列、l1_status 锁、hash ledger） | Codex |
| heng-guan Prisma schema 扩展 + NestJS 端点 | Codex |
| Vue 3 新页面（手动录入 / L1 改进池 / 改分） | Codex |
| 服务器环境配置（systemd、目录、凭据、git clone） | Codex |

git-baseline 交接契约：本仓与语义关系 preview 线共用同一物理仓。
本线在 `feat/service-deploy` 分支工作，不碰 `state/node3c/` 运行产物。切换/收尾必 commit、status 干净。

---

## 11. 滑坡自审（设计层）

- **动的是源还是视图？** sync 只写 DB（视图/派生消费层），不碰 vault raw（源）。手动录入走正规 L1 入库流，人工内容只是"召回种子"，不直接写 DB。✓
- **有没有 per-pid 硬编码？** 无。增量靠 content-hash 全局规则，dedup 靠三维 fingerprint，改分靠 override 字段（per-pid 值只存在于 DB 数据层，不进代码）。✓
- **常驻规则 vs 一次性快照？** 队列/锁/hash ledger/version 全是常驻机制；首次部署只写 836 篇是一次性数据状态，非规则。✓
- **LLM 判定有没有漏进源？** 无。L2 派生仍只落派生层（vault 1_extracted/business_view + DB），不写 raw（§C）。✓
