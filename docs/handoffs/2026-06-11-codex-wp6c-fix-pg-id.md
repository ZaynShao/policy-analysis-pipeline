# Codex 交接：WP-6c-fix sync_l1_pool 的 PG id 契约修复（侦察+本地代码）

**背景**：resume3 实测 forward sync `0/15`——15 条 pool 行全因 `L1ReviewQueue.id` 非空约束被跳过。B14 单测只验了 SQL 形状，没对过 hengguan 真实表。

**纪律（红线）**：服务器侦察**只读**（information_schema，不打印任何数据行/凭据值）；本地 TDD 红绿分 commit；只许改 `scripts/l1_review_consumer/sync_l1_pool.py` + 对应测试；不合 main 不 push；不碰 vault。

## Step 1 · 服务器侦察（只读）

容器内查 `L1ReviewQueue` 列定义（列名/类型/nullable/default 即可，**不查数据**）：
```bash
cd /root/policy-pipeline-src
docker compose -f docker-compose.server.yml run --rm policy-producer python -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"select column_name, data_type, is_nullable, column_default from information_schema.columns where table_name='L1ReviewQueue' order by ordinal_position\")
[print(r) for r in cur.fetchall()]
"
```

## Step 2 · 按侦察结果分支

- **id 为 text 且无 default**（Prisma cuid 由应用层生成的典型形态）→ 本地修：`build_upsert` 增加 `id` 列，值=确定性派生 `"l1_" + sha1(dedupeKey).hexdigest()[:24]`（幂等：同 dedupeKey 同 id）；红绿测试覆盖 id 出现在 SQL+参数、确定性、不同 dedupeKey 不同 id。
- **id 有 default**（serial/uuid default）→ 说明 0/15 另有原因，停下报告原始错误信息。
- **id 为整型无 default** → 停下报告（表侧修复方案 Claude 定）。

## 回报

stdout：Step 1 列定义原文、走了哪个分支、（如修）红绿 commit + pytest 数字。无需 report 文件。**不做服务器重跑**（Claude 审计合 main 后另发）。
