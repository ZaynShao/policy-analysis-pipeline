# Plan B · heng-guan 集成 实施计划

> **For agentic workers / Codex:** 按任务顺序实施。配套 spec：`docs/superpowers/specs/2026-06-06-service-deploy-design.md`（pipeline 仓）。
> **主战场仓：** `safety-platform`（github.com/gloriahao0909/safety-platform），目录 `services/heng-guan/`。
> **git 约定（该仓 SYSTEM_BOUNDARY.md）：** 从 `master` 切 `feature/heng-pipeline-integration`，commit 前缀 `feat(heng): ...`，PR 合 master，**附前端该懂的描述 + 截图**。
> **最后一个任务（Task 9）在 pipeline 仓**，明确标注，复用 Plan A 原语。

**Goal:** 扩展 heng-guan 承接 pipeline 高精度数据（Route C）：Prisma schema 加 pipeline 字段 + 3 张新表；NestJS 加手动录入/改分/L1 反馈端点；Vue 加对应页面。让前端能消费 pipeline 派生 + 触发人工流。

**Architecture:** DB 是 pipeline↔heng-guan 的契约面与消息总线。NestJS **只读写 DB 行**，不直接碰 vault/队列。手动录入：NestJS 写 `ManualEntryRequest` 行 → pipeline 侧 poller（Task 9）消费、做 vault 查重 + l1_status 检查 + 入 l2_queue、回写状态 → 前端轮询状态。

**Tech Stack:** NestJS + Prisma + PostgreSQL（backend）；Vue 3 + TypeScript + Vite（frontend）；测试按 heng-guan 现有约定（NestJS jest / 前端 vitest）。

**契约纪律:** schema 字段名以本计划 + spec §5.1 为准。任一侧改动同步 spec §5。pipeline 侧 `pg_writer.py`（Plan A Task 7）的列名必须与本计划 Prisma 字段**逐字一致**（camelCase，被 quote）。

---

## 文件结构

```
services/heng-guan/backend/
├── prisma/schema.prisma                        ← 扩展（Task 1）
├── prisma/migrations/<ts>_pipeline_integration ← 新迁移（Task 1）
├── src/policy/policy.controller.ts             ← 加端点（Task 2/3）
├── src/policy/policy.service.ts                ← 加方法（Task 2/3）
├── src/policy/dto/manual-entry.dto.ts          ← 新（Task 2）
├── src/policy/dto/override-importance.dto.ts   ← 新（Task 3）
├── src/feedback/feedback.module.ts             ← 新模块（Task 4）
├── src/feedback/feedback.controller.ts         ← 新（Task 4）
├── src/feedback/feedback.service.ts            ← 新（Task 4）
└── src/app.module.ts                           ← 注册 FeedbackModule（Task 4）

services/heng-guan/frontend/
├── src/api/policy.ts                           ← 扩展类型 + 函数（Task 5）
├── src/api/feedback.ts                         ← 新（Task 5）
├── src/views/policy/ManualEntryModal.vue       ← 新（Task 6）
├── src/views/policy/L1FeedbackPool.vue         ← 新（Task 7）
├── src/views/policy/PolicyDrawer.vue           ← 加改分按钮（Task 8）
└── src/router/index.ts                         ← 加 L1 反馈池路由（Task 7）

政策分析-pipeline/（⚠ 另一个仓）
└── scripts/service/manual_entry_poller.py      ← 新（Task 9）
```

---

## Task 1: Prisma schema 扩展 + 迁移

**Files:**
- Modify: `services/heng-guan/backend/prisma/schema.prisma`
- Create: 迁移目录（prisma migrate 自动生成）

- [ ] **Step 1: Policy model 加字段**

在 `model Policy` 内（现有字段后、关联字段前）追加：

```prisma
  // ===== Pipeline 集成（spec §5.1）=====
  pipelinePid     String?   @unique   // P_2024_NDRC_718；null = 手动录入
  pipelineVersion Int?
  pipelineScores  Json?               // {D1..D6, importance, value_tags}
  pipelineThemes  Json?               // [{id,isPrimary,isComprehensive}]
  pipelineImpact  String?             // ②-B 影响分析
  syncedAt        DateTime?
  importanceOverride PolicyImportance? // 非 null 时前端显示覆盖值
  themeOverrides     Json?             // Phase 2 UI

  semanticRelations   PolicySemanticRelation[] @relation("SemFrom")
  semanticRelatedFrom PolicySemanticRelation[] @relation("SemTo")
  manualRequests      ManualEntryRequest[]
```

- [ ] **Step 2: 加三张新表**

在 schema.prisma 末尾追加：

```prisma
// ===== Pipeline 语义关系（spec §5.2）=====
model PolicySemanticRelation {
  id              String   @id @default(cuid())
  fromPolicyId    String
  toPolicyId      String
  relationType    String   // 9 类：derives_from/extends/iterates/aligns_with/
                           // cites_basis/references/clarifies/supersedes/conflicts_with
  confidence      Float?
  evidence        String?
  pipelineVersion Int?
  fromPolicy      Policy   @relation("SemFrom", fields: [fromPolicyId], references: [id], onDelete: Cascade)
  toPolicy        Policy   @relation("SemTo",   fields: [toPolicyId],   references: [id], onDelete: Cascade)
  createdAt       DateTime @default(now())

  @@unique([fromPolicyId, toPolicyId, relationType])
  @@index([fromPolicyId])
  @@index([toPolicyId])
}

// ===== 手动录入请求生命周期（spec §5.2 / §7）=====
model ManualEntryRequest {
  id             String   @id @default(cuid())
  submittedUrl   String
  submittedTitle String?
  submittedBy    String
  status         String   @default("checking")
  // checking / already_exists / l1_running_queued / processing /
  // completed / feedback_created
  resultPolicy   Policy?  @relation(fields: [resultPolicyId], references: [id])
  resultPolicyId String?
  feedbackId     String?
  note           String?
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt

  @@index([status])
}

// ===== L1 漏采反馈池（spec §5.2 / §7.3）=====
model L1FeedbackQueue {
  id              String    @id @default(cuid())
  reportedUrl     String
  reportedTitle   String?
  reportedBy      String
  expectedChannel String?
  l1ScanDate      DateTime?
  status          String    @default("pending")  // pending / reviewed / resolved
  reviewNote      String?
  createdAt       DateTime  @default(now())
  updatedAt       DateTime  @updatedAt

  @@index([status])
}
```

- [ ] **Step 3: 生成迁移 + 重生成 client**

Run（在 `services/heng-guan/backend/`，需本地 Postgres 起着）：
```bash
pnpm db:up            # 起 DB（若没起）
npx prisma migrate dev --name pipeline_integration
npx prisma generate
```
Expected: 生成 `prisma/migrations/<ts>_pipeline_integration/migration.sql`，client 重生成无类型错误。

- [ ] **Step 4: 验证迁移 SQL 含 override 守卫所需列**

Run: `grep -i "importanceOverride\|pipelinePid\|PolicySemanticRelation" prisma/migrations/*/migration.sql`
Expected: 三者都出现。确认 pipeline 侧 `pg_writer.py` 的列名（`"importanceOverride"` / `"pipelinePid"` / `"PolicySemanticRelation"`）与此**逐字一致**。

- [ ] **Step 5: Commit**

```bash
git add prisma/schema.prisma prisma/migrations/
git commit -m "feat(heng): pipeline 集成 schema — Policy 字段 + 语义关系/手动录入/L1反馈表"
```

---

## Task 2: 手动录入端点（NestJS 只写 DB 行）

**Files:**
- Create: `services/heng-guan/backend/src/policy/dto/manual-entry.dto.ts`
- Modify: `src/policy/policy.service.ts`, `src/policy/policy.controller.ts`

逻辑：`POST /policies/manual-entry` 写一条 `ManualEntryRequest`（status=checking），立即返回 id。真正的 vault 查重/入队由 pipeline poller（Task 9）做。`GET /policies/manual-entry/:id/status` 读该行状态。

- [ ] **Step 1: 写 DTO**

```typescript
// src/policy/dto/manual-entry.dto.ts
import { IsString, IsOptional, IsUrl } from 'class-validator';

export class ManualEntryDto {
  @IsUrl()
  submittedUrl!: string;

  @IsOptional()
  @IsString()
  submittedTitle?: string;

  @IsString()
  submittedBy!: string;
}
```

- [ ] **Step 2: service 加方法**

在 `PolicyService` 内追加：

```typescript
  async createManualEntry(dto: {
    submittedUrl: string;
    submittedTitle?: string;
    submittedBy: string;
  }) {
    return this.prisma.manualEntryRequest.create({
      data: {
        submittedUrl: dto.submittedUrl,
        submittedTitle: dto.submittedTitle,
        submittedBy: dto.submittedBy,
        status: 'checking',
      },
    });
  }

  async getManualEntryStatus(id: string) {
    const req = await this.prisma.manualEntryRequest.findUnique({
      where: { id },
      include: { resultPolicy: { select: { id: true, title: true, pipelinePid: true } } },
    });
    if (!req) throw new NotFoundException('manual entry request not found');
    return req;
  }
```

- [ ] **Step 3: controller 加端点**

在 `PolicyController` 内追加（注意路由顺序：放在 `@Get(':id')` **之前**，避免 `manual-entry` 被当成 id）：

```typescript
  @Post('manual-entry')
  createManualEntry(@Body() dto: ManualEntryDto) {
    return this.policyService.createManualEntry(dto);
  }

  @Get('manual-entry/:id/status')
  manualEntryStatus(@Param('id') id: string) {
    return this.policyService.getManualEntryStatus(id);
  }
```
并在文件顶部 import：`import { ManualEntryDto } from './dto/manual-entry.dto';`

- [ ] **Step 4: 写测试**

```typescript
// src/policy/policy.service.spec.ts（追加或新建，按现有 jest 约定）
// 用现有 PrismaService mock 模式；断言 createManualEntry 写 status='checking'
// 断言 getManualEntryStatus 未找到时抛 NotFoundException
```
Run: `pnpm test policy.service`
Expected: 新增用例 PASS（若该仓暂无 service 单测，按现有测试约定加最小用例；无测试基建则跳过单测、在 Step 5 用 e2e/手测验证端点返回 201 + status=checking）

- [ ] **Step 5: 手测端点**

Run: `pnpm dev:backend` 后
```bash
curl -X POST localhost:3000/policies/manual-entry \
  -H 'Content-Type: application/json' \
  -d '{"submittedUrl":"https://example.gov.cn/p/1","submittedBy":"tester"}'
```
Expected: 返回含 `"status":"checking"` 的 JSON。

- [ ] **Step 6: Commit**

```bash
git add src/policy/dto/manual-entry.dto.ts src/policy/policy.service.ts src/policy/policy.controller.ts
git commit -m "feat(heng): 手动录入端点（写 ManualEntryRequest，pipeline poller 异步处理）"
```

---

## Task 3: 人工改分端点（override-importance）

**Files:**
- Create: `services/heng-guan/backend/src/policy/dto/override-importance.dto.ts`
- Modify: `src/policy/policy.service.ts`, `src/policy/policy.controller.ts`

- [ ] **Step 1: 写 DTO**

```typescript
// src/policy/dto/override-importance.dto.ts
import { IsIn, IsOptional } from 'class-validator';

const LEVELS = ['STRATEGIC', 'MAJOR', 'GENERAL', 'INFO'] as const;

export class OverrideImportanceDto {
  // null = 撤销覆盖，恢复 pipeline 值
  @IsOptional()
  @IsIn(LEVELS)
  importance?: (typeof LEVELS)[number] | null;
}
```

- [ ] **Step 2: service 加方法**

```typescript
  async overrideImportance(id: string, importance: string | null) {
    await this.findById(id); // 验证存在
    return this.prisma.policy.update({
      where: { id },
      data: {
        importanceOverride: importance as any, // null 撤销；非 null 覆盖
      },
      select: { id: true, importance: true, importanceOverride: true },
    });
  }
```

- [ ] **Step 3: controller 加端点**

```typescript
  @Patch(':id/override-importance')
  overrideImportance(@Param('id') id: string, @Body() dto: OverrideImportanceDto) {
    return this.policyService.overrideImportance(id, dto.importance ?? null);
  }
```
顶部 import：`Patch` 加进 `@nestjs/common` 的 import；`import { OverrideImportanceDto } from './dto/override-importance.dto';`

> **权限（Codex 确认）:** spec §7.4 限 HQ_GA / MANAGER。按 heng-guan 现有鉴权方式（账号体系 `/kb/api/auth`）加 guard；若该仓前端尚无角色 guard 基建，先放开 + 留 TODO 注释，不自造鉴权。

- [ ] **Step 4: 手测**

```bash
curl -X PATCH localhost:3000/policies/<id>/override-importance \
  -H 'Content-Type: application/json' -d '{"importance":"STRATEGIC"}'
# 撤销：
curl -X PATCH localhost:3000/policies/<id>/override-importance \
  -H 'Content-Type: application/json' -d '{"importance":null}'
```
Expected: 第一次返回 `importanceOverride: "STRATEGIC"`；撤销后 `importanceOverride: null`。
**关键验证（与 pipeline 协同）:** 设了 override 后跑 pipeline sync（Plan A），确认 `importance` 不被 pipeline 值覆盖。

- [ ] **Step 5: Commit**

```bash
git add src/policy/dto/override-importance.dto.ts src/policy/policy.service.ts src/policy/policy.controller.ts
git commit -m "feat(heng): 人工改分端点 override-importance（含撤销）"
```

---

## Task 4: L1 反馈池端点 + 模块

**Files:**
- Create: `src/feedback/feedback.module.ts`, `feedback.controller.ts`, `feedback.service.ts`
- Modify: `src/app.module.ts`

- [ ] **Step 1: service**

```typescript
// src/feedback/feedback.service.ts
import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class FeedbackService {
  constructor(private readonly prisma: PrismaService) {}

  list(status?: string) {
    return this.prisma.l1FeedbackQueue.findMany({
      where: status ? { status } : undefined,
      orderBy: { createdAt: 'desc' },
    });
  }

  async update(id: string, data: { status?: string; reviewNote?: string }) {
    const exists = await this.prisma.l1FeedbackQueue.findUnique({ where: { id } });
    if (!exists) throw new NotFoundException('feedback not found');
    return this.prisma.l1FeedbackQueue.update({ where: { id }, data });
  }
}
```

- [ ] **Step 2: controller**

```typescript
// src/feedback/feedback.controller.ts
import { Body, Controller, Get, Param, Patch, Query } from '@nestjs/common';
import { FeedbackService } from './feedback.service';

@Controller('feedback/l1')
export class FeedbackController {
  constructor(private readonly feedbackService: FeedbackService) {}

  @Get()
  list(@Query('status') status?: string) {
    return this.feedbackService.list(status);
  }

  @Patch(':id')
  update(
    @Param('id') id: string,
    @Body() body: { status?: string; reviewNote?: string },
  ) {
    return this.feedbackService.update(id, body);
  }
}
```

- [ ] **Step 3: module + 注册**

```typescript
// src/feedback/feedback.module.ts
import { Module } from '@nestjs/common';
import { FeedbackController } from './feedback.controller';
import { FeedbackService } from './feedback.service';

@Module({
  controllers: [FeedbackController],
  providers: [FeedbackService],
})
export class FeedbackModule {}
```
在 `src/app.module.ts` import 并加进 `imports: [...]`：
```typescript
import { FeedbackModule } from './feedback/feedback.module';
// imports 数组里加 FeedbackModule,
```

- [ ] **Step 4: 手测**

Run: `pnpm dev:backend` 后 `curl localhost:3000/feedback/l1`
Expected: 返回 `[]`（空池）或已有反馈数组。

- [ ] **Step 5: Commit**

```bash
git add src/feedback/ src/app.module.ts
git commit -m "feat(heng): L1 漏采反馈池端点（list + update）"
```

---

## Task 5: 前端 API 客户端扩展

**Files:**
- Modify: `services/heng-guan/frontend/src/api/policy.ts`
- Create: `src/api/feedback.ts`

- [ ] **Step 1: policy.ts 扩展类型 + 函数**

在 `PolicyDetail` interface 追加字段：

```typescript
  // pipeline 集成
  pipelinePid?: string;
  pipelineThemes?: Array<{ id: string; isPrimary: boolean; isComprehensive: boolean }>;
  pipelineScores?: Record<string, number>;
  pipelineImpact?: string;
  importanceOverride?: 'STRATEGIC' | 'MAJOR' | 'GENERAL' | 'INFO' | null;
```

文件末尾追加函数：

```typescript
export interface ManualEntryStatus {
  id: string;
  status: 'checking' | 'already_exists' | 'l1_running_queued' | 'processing'
        | 'completed' | 'feedback_created';
  resultPolicy?: { id: string; title: string; pipelinePid?: string };
  note?: string;
}

export function submitManualEntry(body: { submittedUrl: string; submittedTitle?: string; submittedBy: string }) {
  return http.post<{ id: string; status: string }>('/policies/manual-entry', body);
}

export function getManualEntryStatus(id: string) {
  return http.get<ManualEntryStatus>(`/policies/manual-entry/${id}/status`);
}

export function overrideImportance(id: string, importance: string | null) {
  return http.patch(`/policies/${id}/override-importance`, { importance });
}
```
（`http.patch` 若 client.ts 未导出，先在 `src/api/client.ts` 补一个 patch 包装，与现有 get/post 同风格。）

- [ ] **Step 2: feedback.ts**

```typescript
// src/api/feedback.ts
import { http } from './client';

export interface L1Feedback {
  id: string;
  reportedUrl: string;
  reportedTitle?: string;
  reportedBy: string;
  expectedChannel?: string;
  l1ScanDate?: string;
  status: 'pending' | 'reviewed' | 'resolved';
  reviewNote?: string;
  createdAt: string;
}

export function listL1Feedback(status?: string) {
  return http.get<L1Feedback[]>('/feedback/l1', { params: status ? { status } : {} });
}

export function updateL1Feedback(id: string, body: { status?: string; reviewNote?: string }) {
  return http.patch<L1Feedback>(`/feedback/l1/${id}`, body);
}
```

- [ ] **Step 3: 类型检查**

Run: `pnpm -C services/heng-guan/frontend type-check`（或 `vue-tsc --noEmit`）
Expected: 无类型错误。

- [ ] **Step 4: Commit**

```bash
git add src/api/policy.ts src/api/feedback.ts src/api/client.ts
git commit -m "feat(heng): 前端 API — 手动录入/改分/L1反馈 类型与函数"
```

---

## Task 6: 手动录入 Modal（带轮询）

**Files:**
- Create: `services/heng-guan/frontend/src/views/policy/ManualEntryModal.vue`
- Modify: 在政策列表页（`PolicyList.vue` 或 `PolicyTabHeader.vue`）加入口按钮

逻辑：用户填 URL（可选标题）→ 提交 → 每 5s 轮询状态 → 按状态显示结果。复用现有 `NewPolicyModal.vue` 的样式风格。

- [ ] **Step 1: 写组件**

```vue
<!-- src/views/policy/ManualEntryModal.vue -->
<script setup lang="ts">
import { ref, onUnmounted } from 'vue';
import { submitManualEntry, getManualEntryStatus, type ManualEntryStatus } from '../../api/policy';

const emit = defineEmits<{ close: [] }>();
const url = ref('');
const title = ref('');
const submitting = ref(false);
const result = ref<ManualEntryStatus | null>(null);
let timer: ReturnType<typeof setInterval> | null = null;

const STATUS_TEXT: Record<string, string> = {
  checking: '正在核查是否已采集…',
  already_exists: '该政策系统已有',
  l1_running_queued: '采集任务进行中，已加入待复核队列，稍后自动确认',
  processing: '正在抓取并派生…',
  completed: '处理完成',
  feedback_created: 'L1 已扫过该来源但未抓到，已记录改进反馈',
};

async function submit() {
  submitting.value = true;
  const { id } = await submitManualEntry({
    submittedUrl: url.value,
    submittedTitle: title.value || undefined,
    submittedBy: 'current-user', // TODO: 接账号体系当前用户
  });
  poll(id);
}

function poll(id: string) {
  const tick = async () => {
    const st = await getManualEntryStatus(id);
    result.value = st;
    if (['already_exists', 'completed', 'feedback_created'].includes(st.status)) {
      stop();
    }
  };
  tick();
  timer = setInterval(tick, 5000);
}

function stop() {
  if (timer) { clearInterval(timer); timer = null; }
}
onUnmounted(stop);
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <h3>手动录入政策</h3>
      <input v-model="url" placeholder="政策 URL" />
      <input v-model="title" placeholder="标题（可选）" />
      <button :disabled="submitting || !url" @click="submit">提交</button>
      <p v-if="result" class="status">{{ STATUS_TEXT[result.status] }}</p>
      <a v-if="result?.resultPolicy" :href="`/policy/${result.resultPolicy.id}`">查看政策</a>
      <button class="close" @click="emit('close')">关闭</button>
    </div>
  </div>
</template>
```
（样式 class 复用该仓现有 modal 样式；若无全局 modal 样式，照 `NewPolicyModal.vue` 的 scoped style 抄一份最小版。）

- [ ] **Step 2: 列表页加入口**

在政策列表头部加按钮「手动录入」，点击 `showManualEntry = true`，渲染 `<ManualEntryModal v-if="showManualEntry" @close="showManualEntry=false" />`。

- [ ] **Step 3: 手测**

Run: `pnpm dev:frontend`，打开列表 → 点「手动录入」→ 填 URL 提交 → 看到「正在核查…」并每 5s 刷新。
Expected: 状态文案随后端 ManualEntryRequest.status 变化（需 Task 9 poller 跑着才会推进；无 poller 时停在 checking——这是预期）。

- [ ] **Step 4: Commit**

```bash
git add src/views/policy/ManualEntryModal.vue src/views/policy/PolicyList.vue
git commit -m "feat(heng): 手动录入 Modal（5s 轮询状态机）"
```

---

## Task 7: L1 反馈池管理页 + 路由

**Files:**
- Create: `src/views/policy/L1FeedbackPool.vue`
- Modify: `src/router/index.ts`

- [ ] **Step 1: 写页面**

```vue
<!-- src/views/policy/L1FeedbackPool.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { listL1Feedback, updateL1Feedback, type L1Feedback } from '../../api/feedback';

const items = ref<L1Feedback[]>([]);
const filter = ref<string>('pending');

async function load() { items.value = await listL1Feedback(filter.value || undefined); }
async function mark(id: string, status: string) { await updateL1Feedback(id, { status }); await load(); }
onMounted(load);
</script>

<template>
  <div class="l1-feedback-pool">
    <h2>L1 漏采反馈池</h2>
    <select v-model="filter" @change="load">
      <option value="pending">待处理</option>
      <option value="reviewed">已审</option>
      <option value="resolved">已处理</option>
      <option value="">全部</option>
    </select>
    <table>
      <thead><tr><th>URL</th><th>标题</th><th>上报人</th><th>预期渠道</th><th>扫描日</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="it in items" :key="it.id">
          <td><a :href="it.reportedUrl" target="_blank">{{ it.reportedUrl }}</a></td>
          <td>{{ it.reportedTitle }}</td>
          <td>{{ it.reportedBy }}</td>
          <td>{{ it.expectedChannel }}</td>
          <td>{{ it.l1ScanDate }}</td>
          <td>{{ it.status }}</td>
          <td>
            <button @click="mark(it.id, 'reviewed')">标已审</button>
            <button @click="mark(it.id, 'resolved')">标已处理</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
```

- [ ] **Step 2: 加路由**

在 `src/router/index.ts` 的 routes 加：
```typescript
{ path: '/policy/l1-feedback', name: 'l1-feedback', component: () => import('../views/policy/L1FeedbackPool.vue') },
```

- [ ] **Step 3: 手测**

Run: `pnpm dev:frontend`，访问 `/policy/l1-feedback`。
Expected: 渲染表格（空池显示无数据；可先手动往 L1FeedbackQueue 插一条测试数据验证渲染 + 标记按钮）。

- [ ] **Step 4: Commit**

```bash
git add src/views/policy/L1FeedbackPool.vue src/router/index.ts
git commit -m "feat(heng): L1 漏采反馈池管理页 + 路由"
```

---

## Task 8: 政策详情加改分按钮 + pipeline 数据展示

**Files:**
- Modify: `src/views/policy/PolicyDrawer.vue`（政策详情抽屉）

- [ ] **Step 1: 详情展示 pipeline 数据 + 改分**

在 PolicyDrawer 的重要性区块加：若 `importanceOverride` 非空，显示覆盖值 + 「人工标注」角标；否则显示 pipeline `importance`。加「改分」下拉 + 「恢复 pipeline 值」按钮：

```vue
<script setup lang="ts">
// 在现有 setup 内加：
import { overrideImportance } from '../../api/policy';
async function changeImportance(policyId: string, level: string | null) {
  await overrideImportance(policyId, level);
  // 重新拉详情或本地更新 importanceOverride
  emit('refresh');
}
</script>
```
模板（重要性区块）：
```vue
<div class="importance-block">
  <span class="value">{{ policy.importanceOverride ?? policy.importance }}</span>
  <span v-if="policy.importanceOverride" class="badge">人工标注</span>
  <select @change="changeImportance(policy.id, ($event.target as HTMLSelectElement).value || null)">
    <option value="">— 改分 —</option>
    <option value="STRATEGIC">STRATEGIC</option>
    <option value="MAJOR">MAJOR</option>
    <option value="GENERAL">GENERAL</option>
    <option value="INFO">INFO</option>
  </select>
  <button v-if="policy.importanceOverride" @click="changeImportance(policy.id, null)">恢复 pipeline 值</button>
</div>
```
若详情有 `pipelineThemes`，加一个只读主题标签区展示（每个 theme.id，primary 高亮）。

- [ ] **Step 2: 类型检查**

Run: `pnpm -C services/heng-guan/frontend type-check`
Expected: 无类型错误。

- [ ] **Step 3: 手测**

打开任一政策详情 → 选「改分」→ STRATEGIC → 显示覆盖值 + 角标 → 点「恢复」→ 回到 pipeline 值。

- [ ] **Step 4: Commit**

```bash
git add src/views/policy/PolicyDrawer.vue
git commit -m "feat(heng): 政策详情展示 pipeline 主题 + 人工改分/恢复"
```

---

## Task 9: ⚠ pipeline 仓 · manual_entry_poller（复用 Plan A 原语）

> **此任务在 pipeline 仓**（`政策分析-pipeline`，分支 `feat/service-deploy`），不是 safety-platform。
> 它是手动录入流的 pipeline 侧消费者：DB 当消息总线。

**Files:**
- Create: `scripts/service/manual_entry_poller.py`
- Test: `tests/service/test_manual_entry_poller.py`

逻辑（spec §7.1，注入式以便测试）：轮询 `ManualEntryRequest` 表 status=checking 的行 → 对每条：
1. 读 l1_status：running → 更新 status=`l1_running_queued`（留待 L1 完成后由同一 poller 重扫）。
2. idle → 查 vault 0_raw 三维 dedup（复用现有 l1_collect dedup）：
   - 命中 → status=`already_exists` + resultPolicyId（用命中 pid 找 Policy）。
   - 未命中 → 判断 L1 是否扫过该来源：扫过 → 写 L1FeedbackQueue + status=`feedback_created`；没扫过 → 入 l2_queue（high）+ status=`processing`。

- [ ] **Step 1: 写失败测试（注入式纯逻辑）**

```python
# tests/service/test_manual_entry_poller.py
from scripts.service.manual_entry_poller import decide_action, Decision

def test_l1_running_defers():
    d = decide_action(url="u", l1_running=True, vault_hit=None, l1_scanned_source=False)
    assert d.status == "l1_running_queued"

def test_idle_vault_hit_already_exists():
    d = decide_action(url="u", l1_running=False, vault_hit="P_2024_NDRC_718", l1_scanned_source=False)
    assert d.status == "already_exists"
    assert d.result_pid == "P_2024_NDRC_718"

def test_idle_miss_scanned_feedback():
    d = decide_action(url="u", l1_running=False, vault_hit=None, l1_scanned_source=True)
    assert d.status == "feedback_created"

def test_idle_miss_not_scanned_processing():
    d = decide_action(url="u", l1_running=False, vault_hit=None, l1_scanned_source=False)
    assert d.status == "processing"
    assert d.enqueue is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/service/test_manual_entry_poller.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现（决策纯函数 + DB/vault 副作用薄封装）**

```python
# scripts/service/manual_entry_poller.py
"""手动录入流的 pipeline 侧消费者。DB(ManualEntryRequest) 当消息总线。

decide_action 是纯决策函数（重测）；DB 轮询 + vault dedup + 入队为薄封装。
vault 三维 dedup 复用现有 l1_collect dedup（不重造，见 LESSONS B2/B7）。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Decision:
    status: str               # already_exists / l1_running_queued / processing / feedback_created
    result_pid: str | None = None
    enqueue: bool = False


def decide_action(url: str, l1_running: bool, vault_hit: str | None,
                  l1_scanned_source: bool) -> Decision:
    if l1_running:
        return Decision(status="l1_running_queued")
    if vault_hit:
        return Decision(status="already_exists", result_pid=vault_hit)
    if l1_scanned_source:
        return Decision(status="feedback_created")
    return Decision(status="processing", enqueue=True)
```

> **Codex 落地补全（副作用层，集成测，无 DB/vault 时 skip）:** 加 `poll_once(conn, vault, l1_status_path, queue_path)`：
> SELECT checking 行 → 对每行调 `decide_action`（vault_hit 来自现有 l1_collect dedup；l1_scanned_source 来自渠道扫描记录）→ 按 Decision 更新行 / 写 L1FeedbackQueue / `l2_queue.enqueue(..., priority="high")`。
> 用现有 `scripts.service.l2_queue` + `l1_status` + l1_collect dedup，不新造。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/service/test_manual_entry_poller.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: principle_guard + commit**

```bash
python3 -m scripts.audit.principle_guard scripts/service
git add scripts/service/manual_entry_poller.py tests/service/test_manual_entry_poller.py
git commit -m "feat(service): manual_entry_poller 决策核心（DB 消息总线消费者）"
```

---

## Self-Review（对 spec 核对）

**Spec 覆盖：**
- §5.1 Policy 新字段 → Task 1 ✓
- §5.2 三张新表 → Task 1 ✓
- §5.4 字段映射（pipeline 侧）→ 列名与本计划逐字一致（Task 1 Step 4 校验）✓
- §7.1 手动录入落 L1 收尾 + 状态机 → Task 2（端点）+ Task 9（poller 决策）✓
- §7.2 端点 + 5s 轮询 → Task 2 + Task 6 ✓
- §7.3 L1 改进池页 → Task 4 + Task 7 ✓
- §7.4 改分 + 撤销 + override 守卫协同 → Task 3 + Task 8 ✓

**已知 scope 边界（非 gap）：**
- 权限 guard（HQ_GA/MANAGER）→ 接 heng-guan 现有账号体系；无基建则放开 + TODO（Task 3 已注明）。
- `current-user` 取当前登录用户 → 接账号体系（Task 6 TODO 注明）。
- 主题人工覆盖 UI（themeOverrides）→ Phase 2（spec §9）。

**跨仓依赖：** Task 9 在 pipeline 仓，依赖 Plan A 的 l2_queue/l1_status 原语 + Task 1 的 ManualEntryRequest 表。三者就绪后手动录入流端到端通。

**类型一致性：** ManualEntryRequest.status 枚举值（checking/already_exists/l1_running_queued/processing/completed/feedback_created）在 schema(Task1)/service(Task2)/前端(Task5)/poller(Task9) 四处一致；PolicyImportance 枚举（STRATEGIC/MAJOR/GENERAL/INFO）在 schema/DTO/前端/pipeline mapper(Plan A Task5) 一致。
