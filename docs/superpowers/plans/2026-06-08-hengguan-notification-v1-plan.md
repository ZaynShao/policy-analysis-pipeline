# hengguan 简易消息 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Steps use checkbox (`- [ ]`).
> **分工**:Task 1-3 = Codex 在 **safety-platform 仓**(新 PR `feat(heng): 内建消息v1`)·TDD;Task 4 = Codex 在 **pipeline 仓**·TDD;Claude 审。
> **spec**:`docs/superpowers/specs/2026-06-08-hengguan-notification-v1-design.md`
> **现有套路(必须沿用)**:后端模块 = `backend/src/<m>/<m>.{controller,service,module}.ts` + `dto/`,Prisma 经 `backend/src/prisma` 的 PrismaService;角色 = `req.user.role`(由 `common/guards/jwt-auth.guard.ts` 注入,**无独立 RolesGuard**→MANAGER 用 inline 检查,参 `workbench.controller.ts` 读 `req.user`)。前端角色 = `stores/user.ts` 的 `useUserStore().current?.role`;顶栏 = `components/layout/TopBar.vue`;API 层参 `api/workbench.ts`;toast 参 `stores/toast.ts`。

**Goal:** hengguan 内建最简"消息":run_sync 失败写一条 Notification 进 heng-pg,MANAGER 在前端铃铛看到、可标已读。替代外部飞书告警。

**Architecture:** run_sync(Tokyo 容器,失败时)直写 `Notification` 表 → NestJS `GET/PATCH /notifications`(MANAGER inline 守卫)→ Vue TopBar 铃铛 + 列表(MANAGER-only)。

**Tech Stack:** Prisma + PostgreSQL、NestJS 10、Vue3 + Pinia、psycopg2(pipeline 侧直写)。

---

## File Structure

**safety-platform 仓(新 PR):**
- `services/heng-guan/backend/prisma/schema.prisma`(改:+ `Notification` model + `NotificationLevel` enum)
- `services/heng-guan/backend/prisma/migrations/<ts>_notification/migration.sql`(新)
- `services/heng-guan/backend/src/notification/notification.{module,service,controller}.ts`(新)+ `dto/list-notifications.dto.ts`
- `services/heng-guan/backend/src/app.module.ts`(改:注册 NotificationModule)
- `services/heng-guan/frontend/src/api/notification.ts`(新)
- `services/heng-guan/frontend/src/components/layout/TopBar.vue`(改:加铃铛+红点+下拉,MANAGER-only)

**pipeline 仓:**
- `scripts/sync/pg_writer.py`(改:+ `build_notification_insert`)
- `scripts/sync/run_sync.py`(改:失败路径写一条 Notification)
- `tests/sync/test_pg_writer.py` / `tests/sync/test_run_sync.py`(改:加测试)

---

## Task 1: schema —— Notification 表(Codex · safety-platform)

**Files:** `services/heng-guan/backend/prisma/schema.prisma`、新迁移目录

- [ ] **Step 1:加 enum + model**(schema.prisma 末尾):

```prisma
enum NotificationLevel {
  INFO
  WARN
  ERROR
}

model Notification {
  id           String            @id @default(cuid())
  level        NotificationLevel @default(INFO)
  title        String
  body         String?
  source       String
  createdAt    DateTime          @default(now())
  readAt       DateTime?
  targetRole   UserRole?         // null = 默认对 MANAGER 可见;v1 不实现路由
  targetUserId String?           // 后期"推开发owner"用
  @@index([readAt])
  @@index([createdAt])
}
```

- [ ] **Step 2:生成迁移(非交互,同 PR#14 方式)**

Run(本地 heng_dev):
```bash
cd services/heng-guan/backend
npx prisma migrate diff --from-schema-datasource prisma/schema.prisma --to-schema-datamodel prisma/schema.prisma --script > /tmp/_notif.sql   # 或用 migrate dev --create-only 等价生成
# 实际用与 PR#14 相同的 migrate diff(origin/master schema → 当前)--script 生成确定性 delta,落 migrations/<ts>_notification/migration.sql
npx prisma migrate deploy
npx prisma migrate status   # up to date
npx prisma validate         # valid
```
Expected:`Notification` 表 + `NotificationLevel` enum 建成;status up-to-date。

- [ ] **Step 3:提交**(commit 前缀 `feat(heng):`,PR 标 `[DB-MIGRATION]`)

```bash
git add prisma/schema.prisma prisma/migrations
git commit -m "feat(heng): Notification 表(内建消息v1)[DB-MIGRATION]"
```

---

## Task 2: 后端 NotificationModule(Codex · safety-platform · TDD)

**Files:** `backend/src/notification/notification.{module,service,controller}.ts` + `dto/` ;改 `app.module.ts`

- [ ] **Step 1:service 失败测试**(参现有 service spec 风格;PrismaService 用测试库或 mock)

`notification.service.spec.ts`:
```typescript
// 行为:list(role) 返回 targetRole 为 null 或 == role 的,按 createdAt desc,带 unreadCount;markRead 置 readAt
describe('NotificationService', () => {
  it('list 只返回 targetRole null 或匹配角色的,unreadCount 数未读', async () => {
    // seed: A(targetRole null, readAt null), B(targetRole MANAGER, readAt set), C(targetRole OPERATOR)
    const r = await service.list('MANAGER', { limit: 50 });
    expect(r.items.map(i => i.id).sort()).toEqual(['A','B'].sort());
    expect(r.unreadCount).toBe(1); // 只有 A 未读
  });
  it('markRead 置 readAt', async () => {
    await service.markRead('A');
    const a = await prisma.notification.findUnique({ where: { id: 'A' } });
    expect(a!.readAt).not.toBeNull();
  });
});
```

- [ ] **Step 2:跑测试确认失败**(模块不存在)。

- [ ] **Step 3:实现 service**

`notification.service.ts`(注入 PrismaService,参其它 service):
```typescript
@Injectable()
export class NotificationService {
  constructor(private prisma: PrismaService) {}
  async list(role: string, q: { unreadOnly?: boolean; limit?: number }) {
    const visible = { OR: [{ targetRole: null }, { targetRole: role as any }] };
    const where = q.unreadOnly ? { AND: [visible, { readAt: null }] } : visible;
    const [items, unreadCount] = await Promise.all([
      this.prisma.notification.findMany({ where, orderBy: { createdAt: 'desc' }, take: q.limit ?? 50 }),
      this.prisma.notification.count({ where: { AND: [visible, { readAt: null }] } }),
    ]);
    return { items, unreadCount };
  }
  markRead(id: string) {
    return this.prisma.notification.update({ where: { id }, data: { readAt: new Date() } });
  }
}
```

- [ ] **Step 4:controller(MANAGER inline 守卫,参 workbench.controller 读 req.user)**

`notification.controller.ts`:
```typescript
@UseGuards(JwtAuthGuard)
@Controller('notifications')
export class NotificationController {
  constructor(private svc: NotificationService) {}
  private assertManager(req: any) {
    if (req.user?.role !== 'MANAGER') throw new ForbiddenException('仅管理员可见');
  }
  @Get()
  list(@Req() req: any, @Query('unreadOnly') unreadOnly?: string, @Query('limit') limit?: string) {
    this.assertManager(req);
    return this.svc.list(req.user.role, { unreadOnly: unreadOnly === 'true', limit: limit ? +limit : 50 });
  }
  @Patch(':id/read')
  read(@Req() req: any, @Param('id') id: string) {
    this.assertManager(req);
    return this.svc.markRead(id);
  }
}
```

- [ ] **Step 5:module + 注册**

`notification.module.ts`(providers: service, controllers: controller, imports PrismaModule 同其它模块);`app.module.ts` imports NotificationModule。

- [ ] **Step 6:controller 守卫测试**:非 MANAGER 调 GET → 403;MANAGER → 200。跑全测试绿。

- [ ] **Step 7:提交** `feat(heng): 消息 API(list/markRead,MANAGER 守卫)`

---

## Task 3: 前端 铃铛 + 列表(Codex · safety-platform)

**Files:** `frontend/src/api/notification.ts`(新)、`components/layout/TopBar.vue`(改)

- [ ] **Step 1:API 层**(参 `api/workbench.ts`)

`api/notification.ts`:
```typescript
import { http } from './http'; // 沿用现有 http 封装
export const notificationApi = {
  list: (unreadOnly = false) => http.get('/notifications', { params: { unreadOnly } }).then(r => r.data),
  markRead: (id: string) => http.patch(`/notifications/${id}/read`).then(r => r.data),
};
```
(若现有 api 不是 `http` 而是别的封装,按实际改;参 workbench.ts 的导出/调用方式。)

- [ ] **Step 2:TopBar 加铃铛(MANAGER-only)**

`TopBar.vue` 改:
- `import { useUserStore } from '@/stores/user'` → `const isManager = computed(() => userStore.current?.role === 'MANAGER')`。
- 模板里 `v-if="isManager"` 渲染一个铃铛图标 + 未读红点(`unreadCount` from `notificationApi.list(true)`,进入/轮询拉)。
- 点击 → 下拉/抽屉列消息(level/title/body/createdAt),点条目 → `notificationApi.markRead(id)` 后本地置已读、红点减。
- 沿用现有 TopBar 的样式/交互风格,不引新组件库。

- [ ] **Step 3:手验**:MANAGER 账号见铃铛 + 红点;非 MANAGER 不见铃铛;标已读后红点减。`vite build` 过(注意现有 toast 'warning' 历史告警与本改无关)。

- [ ] **Step 4:提交** `feat(heng): TopBar 消息铃铛+列表(MANAGER 可见)`

---

## Task 4: pipeline 侧 run_sync 失败写消息(Codex · pipeline 仓 · TDD)

**Files:** `scripts/sync/pg_writer.py`、`scripts/sync/run_sync.py`、对应测试

- [ ] **Step 1:build_notification_insert 失败测试**

`tests/sync/test_pg_writer.py` 加:
```python
def test_build_notification_insert():
    from scripts.sync.pg_writer import build_notification_insert
    sql, params = build_notification_insert(level="ERROR", title="run_sync 失败", body="2 errors", source="sync")
    assert '"Notification"' in sql
    assert 'gen_random_uuid()::text' in sql           # id 必须自带(cuid 非 DB 默认)
    assert '"createdAt"' not in sql                    # createdAt 走 DB 默认 now(),不传
    assert '::"NotificationLevel"' in sql              # enum 转型
    assert params["level"] == "ERROR" and params["source"] == "sync"
```

- [ ] **Step 2:跑确认失败**。

- [ ] **Step 3:实现 build_notification_insert**

`pg_writer.py` 加:
```python
def build_notification_insert(*, level: str, title: str, body, source: str):
    """生成插入一条 Notification 的 SQL+params。
    id 自带(Prisma cuid 非 DB 默认→gen_random_uuid);createdAt 走 DB 默认 now();readAt 默认 NULL。
    """
    sql = (
        'INSERT INTO "Notification" ("id","level","title","body","source") '
        'VALUES (gen_random_uuid()::text, %(level)s::"NotificationLevel", %(title)s, %(body)s, %(source)s)'
    )
    return sql, {"level": level, "title": title, "body": body, "source": source}
```

- [ ] **Step 4:跑确认通过**。

- [ ] **Step 5:run_sync 失败路径写消息**

`run_sync.py` 的 `run()`:在 `conn.commit()` 之后、`conn.close()`(finally)之前,加:
```python
        if errors:
            try:
                title = f"run_sync 失败:{len(errors)} 条错误"
                body = ("; ".join(errors))[:1000]
                if skipped_rows:
                    body += f"(另 skipped_invalid={len(skipped_rows)})"
                nsql, nparams = pg_writer.build_notification_insert(
                    level="ERROR", title=title, body=body, source="sync")
                pg_writer.execute_with_savepoint(conn, nsql, nparams)
                conn.commit()
            except Exception as e:           # 写消息失败绝不崩 sync
                errors.append(f"notification write failed: {e}")
```
（注:此段在现有 try 内、`conn.commit()` 之后;`execute_with_savepoint` 已有。）

- [ ] **Step 6:run_sync 测试**

`tests/sync/test_run_sync.py` 加(用 fake conn/cursor,不连真库):失败有 errors 时,执行序列里包含一次 Notification INSERT;且当 Notification 写入抛错时 `run()` 不抛、把错记进 errors。

- [ ] **Step 7:principle_guard + 提交**

```bash
python3 -m scripts.audit.principle_guard scripts/sync
git commit -m "feat(sync): run_sync 失败写 Notification 消息(配合 hengguan 消息v1)"
```

---

## Self-Review

- **Spec 覆盖**:schema=Task1;后端 list/markRead+MANAGER 守卫=Task2;前端铃铛/列表 MANAGER-only=Task3;run_sync 直写=Task4;扩展位 targetRole/targetUserId=Task1(留字段不实现路由,符 v1)。✅
- **占位扫描**:框架样板(http 封装名/TopBar 具体 DOM/service spec 的 PrismaService 接法)指向"参现有 X 文件",因 Codex 在仓内按真实模式落——这是本项目 Codex 工作流的正确粒度,非占位漏洞;确定性部分(Prisma schema、SQL、pipeline 测试)给了完整代码。
- **类型一致**:`build_notification_insert` 在 Task4 测试与实现签名一致;`NotificationLevel` enum 值(INFO/WARN/ERROR)前后一致;前端 role 取 `useUserStore().current?.role` 与后端 `req.user.role` 同口径('MANAGER')。
- **跨仓契约**:Task4 的 SQL 列名(`"Notification"`/`"level"`/`"title"`/`"body"`/`"source"`)必须与 Task1 迁移落地的真实列名核对(沿用 Policy sync 列名对账纪律)——迁移落地后定稿 INSERT。
