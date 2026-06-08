# hengguan 简易"消息" v1 设计 spec

> 2026-06-08 · Stage 1 的告警出口(替代飞书)· 与 `2026-06-08-stage1-continuous-sync-design.md` 并行 · 待用户复核 → writing-plans
> 实施落 **safety-platform 仓**(hengguan),走**单独一个新 PR**(非并入 PR #14)。

## Goal

给 hengguan 加一个**最简内建"消息"**功能:run_sync(以及未来其它系统事件)失败/异常时,写一条消息进 heng-pg,**管理员(MANAGER 角色)在前端能看到**。替代外部飞书告警——告警留在用户天天看的系统内,零外部依赖。

成功标准:run_sync 失败 → heng-pg 多一条 Notification → MANAGER 登录前端看到红点 + 消息列表 → 可标已读。非 MANAGER 看不到。

## 决策(已拍)

- 收件可见角色:**MANAGER**(UserRole 无 ADMIN,MANAGER 最接近管理员)。
- PR:**单开一个新 PR**(不绑 PR #14)。
- 次序:**管道先上 staging(告警暂用 last_sync_run.json),本消息功能并行做,cutover 前接上**。
- 前期推管理员;**后期**改/加"推开发 owner"——v1 留扩展字段,不实现路由逻辑。
- 范围钉死:**v1 只服务 run_sync 告警 + 管理员可见的最简列表**,不做通用通知中台(防膨胀)。但 schema 设计保留通用性(未来 RSS token 失效、L1 反馈、人工录入状态 = B14 各池 都能复用此出口)。

## Architecture

```
run_sync(Tokyo 容器,失败时)
   └─ 直接 INSERT 一行 Notification → heng-pg   (沿用 run_sync 已有的直连库方式,不走 API)
hengguan 后端(NestJS)
   └─ GET /notifications(MANAGER 守卫:列最近 + 未读数)
   └─ PATCH /notifications/:id/read(标已读)
hengguan 前端(Vue3)
   └─ 顶部红点(未读数)+ 消息列表视图,MANAGER 角色可见
```

## Components

### 1. schema(Prisma 迁移,新 PR,`[DB-MIGRATION]`)
新 model `Notification`:
```prisma
enum NotificationLevel { INFO  WARN  ERROR }

model Notification {
  id        String            @id @default(cuid())
  level     NotificationLevel @default(INFO)
  title     String
  body      String?           // 详情(如 run_sync errors 摘要)
  source    String            // "sync" | 未来 "rss" | "l1feedback" ...
  createdAt DateTime          @default(now())
  readAt    DateTime?         // null = 未读
  // 扩展位(v1 不实现路由,仅留字段)
  targetRole UserRole?        // 默认对 MANAGER 可见;后期可指定其它
  targetUserId String?        // 后期"推开发 owner"用
  @@index([readAt])
  @@index([createdAt])
}
```
- 迁移用 `migrate diff → migrate deploy`(同 PR #14 的非交互方式),先本地 heng_dev,再随 PR 进 staging/生产。

### 2. 后端(NestJS · `services/heng-guan/backend`)
- 新 `NotificationModule`:
  - `GET /notifications?unreadOnly=&limit=` → MANAGER 守卫(复用现有 role guard);返回最近 N 条 + `unreadCount`。可见性:`targetRole IS NULL`(默认全 MANAGER 可见)OR `targetRole = 调用者角色`。
  - `PATCH /notifications/:id/read` → 置 readAt = now。
  - **v1 不提供 create 端点**:run_sync 直写库(见下)。若日后非直连源要写,再加内部 create 端点。
- 守卫:沿用 hengguan 既有的角色守卫机制(MANAGER)。遵守 SYSTEM_BOUNDARY:本功能完全在 heng-guan 模块内,不跨模块。

### 3. 前端(Vue3 · `services/heng-guan/frontend`)
- 顶部栏(workbench/shell)加一个**铃铛 + 未读红点**,仅当 `user.role === 'MANAGER'` 渲染。
- 一个**消息列表视图/抽屉**:列 level/title/body/createdAt,点击标已读;轮询或进入时拉 `GET /notifications`。
- 最简实现,沿用现有 UI 风格(无需新组件库)。

### 4. run_sync 侧写消息(pipeline 仓)
- run_sync 当轮 `errors` 非空(或抛异常)时,**INSERT 一行 Notification**:
  - level=ERROR,source="sync",title 如 `"run_sync 失败:N 条错误"`,body=errors 摘要(截断)+ skipped_invalid 计数。
  - 复用 run_sync 已有的 psycopg2 连接 + SAVEPOINT 方式;新增 `pg_writer.build_notification_insert(...)`(纯 SQL 字符串,单测,不连库)。
  - ⚠️ 列名/默认值对账(**沿用 Policy sync 教训**):raw INSERT **必须自带 `id`**(Prisma `@default(cuid())` 不产生 DB 级默认 → 用 `gen_random_uuid()::text`);`createdAt` 的 `@default(now())` **有 DB 级默认 → 可省略**;列名为带引号 camelCase(`"createdAt"` / `"readAt"`)。迁移落地后拿真实 schema 复核一遍再定稿 INSERT。
  - 失败兜底:连写 Notification 都失败时,**不能再抛**(避免告警自身崩 sync 进程)→ try/except 包住,落 last_sync_run.json + stderr。

## Data flow

1. sync_tick 跑 run_sync。
2. run_sync 检测 errors 非空 → build_notification_insert → 直写 heng-pg(同库同事务边界,SAVEPOINT 隔离)。
3. MANAGER 登录前端 → 铃铛红点 → 看列表 → 标已读。

## Testing / 验收

- **后端**:GET 列表(MANAGER 可见 / 非 MANAGER 403 或空)、未读数、PATCH 标已读;不连真库用测试库或 mock。
- **前端**:role===MANAGER 才渲染铃铛;未读红点数;标已读后红点减。
- **run_sync 写消息(pipeline 仓)**:`build_notification_insert` 单测(SQL 列对齐、值占位、level=ERROR);run_sync 失败路径 → 写一行(集成,对 heng_dev/staging)。写消息失败不崩 sync(注入坏连接,断言 sync 仍返回 + 记 stderr)。
- **端到端(staging)**:故意坏 DATABASE_URL 子句造 run_sync 部分失败 → staging heng-pg 出现 ERROR Notification → 前端 MANAGER 看到。

## Risks / 约束

- **又一个 hengguan PR**:schema(`[DB-MIGRATION]`)+ 后端 + 前端,过 gloriahao0909 治理。比飞书 webhook 重(用户已知并选择此路)。
- **直连库 vs SYSTEM_BOUNDARY "走 API"**:run_sync 直写 Notification 与边界规则"模块走 API"有张力(同 Policy sync 的既有张力);v1 维持直写(性能/一致),PR 描述里说明。若前端团队要求走 API,则 run_sync 改调一个内部 create 端点(成本略增)。
- **列名/默认值对账**:迁移后必须拿真实 schema 核 pg_writer 的列名(重复 Policy sync 那次教训)。
- **范围蔓延**:v1 严格只做 run_sync 告警 + MANAGER 列表;通用通知中台 / B14 各池接入 = 后续,不在 v1。

## 落地物

- safety-platform 仓(新 PR `feat(heng): 内建消息 v1`):schema 迁移 + NotificationModule + 前端铃铛/列表。
- pipeline 仓:`pg_writer.build_notification_insert` + run_sync 失败写消息 + 测试。
- 文档:本 spec;PR 描述写清直连库取舍 + 列名对账。
