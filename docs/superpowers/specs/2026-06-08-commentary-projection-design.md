# 评论信号投影（CommentarySignal projection）设计

**日期**：2026-06-08
**状态**：设计已确认，待写实现 plan
**前置**：生产 hengguan 已部署 pipeline schema（PR#14/#16/#17，db push 完成）；run_sync 已投政策 + 政策↔政策语义关系。

## Goal

把 vault 的评论信号（`1_extracted/commentary_signals.jsonl`）投影进衡观数据库，使评论在生产**被录入**并随每晚 run_sync 持续同步。**本期 backend-only，不做前端**；表结构对未来「政策详情显示相关评论」视图**前向兼容、零返工**。

## 背景与约束（实测）

- 评论信号共 **171 条**，全部带 `related_policy_ids`（261 条评论→政策边）。
- 261 条边中 **174 指向已存在政策、87（33%）指向 vault 里尚不存在的政策**（评论先入 / 政策未采）。
- 衡观当前**没有任何评论表**；评论链接只在 vault jsonl，从未进过 DB。
- 本地历史消费评论 = 报告/HTML 预览（`derived_signals/report.py`、`signal_context`），无 DB/前端先例。

**核心约束**：政策链接必须是**软引用**（存 pid 字符串，读时解析），不能像 run_sync 投关系那样「一端政策不在就硬跳过」——否则丢掉 33% 的边，且引入 sync 时序依赖。

## 关键设计决策

1. **CommentarySignal 做一等公民表**：每条信号一行，自带元数据（标题/证据/role/置信/来源/主题/业务线）。信号独立存在，**不依赖其关联政策是否在库**。
2. **政策链接 = 软引用**：`relatedPolicyPids` 存 pid 字符串数组（Json），**不建外键、不在 sync 时解析、不跳过悬挂**。
3. **读时解析**：未来「政策 → 相关评论」是一条读查询（`WHERE 该政策pid ∈ relatedPolicyPids`）。政策后入库时链接自动亮，无需重 sync 评论。
4. **sync 搭 run_sync 的车**：评论投影作为 run_sync 的第三个 collector，与政策同一条 cron、同一次部署。
5. **不做前端**：未来「政策详情显示相关政策 + 评论」的评论一半，是纯增量读视图。

## 数据流

```
vault 1_extracted/commentary_signals.jsonl
   → run_sync.collect_commentary_rows（读 + 映射）
   → pg_writer.build_commentary_upsert（按 commentaryId upsert）
   → heng-pg CommentarySignal 表
   → (未来) 前端政策详情读时解析 relatedPolicyPids → 显示相关评论
```

## 组件

### 1. 衡观新表 `CommentarySignal`（hengguan schema + 迁移）

| 字段 | 类型 | 来源（jsonl） | 说明 |
|---|---|---|---|
| `id` | String @id @default(cuid()) | — | 主键 |
| `commentaryId` | String @unique | `commentary_id` | 幂等键（如 C_0d474bd19965） |
| `title` | String | `title` | 标题 |
| `evidence` | String? | `evidence` | 评论摘录 |
| `signalRole` | String? | `signal_role` | opportunity / risk / execution |
| `confidence` | Float? | `confidence` | 置信度 |
| `sourceAccount` | String? | `source_account` | 来源公众号 |
| `businessTag` | String? | `business_tag` | 自由值·实测 power(39)/cross(16)/gas(1)/空(115) |
| `themeIds` | Json? | `theme_ids` | 主题 id 数组 |
| `relatedPolicyPids` | Json | `related_policy_ids` | **软引用**·政策 pid 字符串数组 |
| `sourcePath` | String? | `path` / `sanitized_from` | 溯源原始评论路径 |
| `pipelineVersion` | Int? | — | 版本 |
| `syncedAt` | DateTime? | — | 最近同步时间 |
| `createdAt` | DateTime @default(now()) | — | — |

索引：`@@index([businessTag])`、`@@index([signalRole])`（便于未来按业务线/信号类型筛）。`commentaryId` 唯一索引已隐含。

**前向兼容说明**：`relatedPolicyPids` 用 Json 数组存储。未来「政策 → 相关评论」查询用 jsonb 包含（`relatedPolicyPids @> '["P_xxx"]'`）；若需提速，**后续可加 GIN 索引或派生 join 表——均为 additive 迁移，不改本表、不重灌数据**。这满足「后续后端不影响」。

### 2. pipeline sync 扩展（`scripts/sync/`）

- `run_sync.collect_commentary_rows(vault, pipeline_version) -> list[dict]`：读 `1_extracted/commentary_signals.jsonl`，逐行映射为行 dict（jsonl 字段 → 表字段）。`relatedPolicyPids` / `themeIds` 原样作为列表带上（写库时序列化为 Json）。**不做政策解析、不跳过悬挂边。**
- `pg_writer.build_commentary_upsert(row) -> (sql, params)`：`INSERT INTO "CommentarySignal" (...) VALUES (...) ON CONFLICT ("commentaryId") DO UPDATE SET ...`（幂等，重跑更新）。Json 字段用 `json.dumps` 序列化或 psycopg2 Json 适配。
- `run_sync.run()`：在政策 + 关系投影之后，新增评论投影段——`collect_commentary_rows` → 逐行 `build_commentary_upsert` + `execute_with_savepoint`，**单条失败不崩整批**（try/except，错误入 `errors`，与 policy 行一致）；计数进 summary（`commentary_count`）。

**不改** `sync_tick` / 既有 policy/relation 逻辑。复用既有 psycopg2 + savepoint 写法。

### 3. 部署

- 衡观侧：`CommentarySignal` model + 迁移 → **PR 给 gloriahao0909**（从 master 切，[DB-MIGRATION]）→ 合并后生产 `db push` 补这张表（一次轻量部署，或并入下次部署）。
- pipeline 侧：run_sync 扩展 → PR → 合并 main → 随服务器 git pull + 镜像重建生效，跟政策同一条每晚 cron。

## 错误处理

- 评论投影**整段在 try/except 内逐行容错**：单条信号写失败 → 记 `errors`，继续下一条。
- 表不存在（部署前）→ 全部失败但**不影响政策/关系投影**（独立段）；部署后自然恢复。
- 这与既有 run_sync「单篇 policy 失败不崩整批」一致。

## 测试

**pipeline（pytest）**：
- `collect_commentary_rows`：给一个临时 jsonl（含悬挂政策的信号）→ 断言映射正确、悬挂的 `relatedPolicyPids` **原样保留不丢**。
- `build_commentary_upsert`：断言 SQL 含 `ON CONFLICT ("commentaryId")`、params 含全部字段、Json 字段正确序列化。
- run 集成：mock 连接，断言评论段被调用、计数进 summary、单条失败被 try/except 兜住不崩。

**衡观**：迁移 `prisma validate` 通过；schema 形状自检。

## Out of scope（本期不做）

- 前端（任何评论展示视图）。
- 独立「舆情列表」页。
- 评论↔政策 join 表 / GIN 索引（未来按需 additive 加）。
- 原始 401 篇评论 md 的投影（只投 171 条结晶信号）。
- 评论的人工审核 / 回灌（与 B14 L1 审核是两回事）。

## 前向兼容保证（回应「后续后端不影响」）

未来做「政策详情显示相关评论」时：
- 是一条**读查询**（按 pid 解析 `relatedPolicyPids`），不动表结构、不动 sync、不重灌。
- 若需查询提速：加 GIN 索引或派生 join 表，**均为 additive**，不破坏本表。

故本期把录入做扎实即可，前端纯增量。
