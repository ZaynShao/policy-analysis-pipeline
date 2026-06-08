# 评论信号投影（CommentarySignal projection）实现 Plan

> **For agentic workers:** 本项目用 Codex 执行（Claude 设计/审计）。每个 Task 转成一个 Codex 提示词，Codex TDD 实现，Claude 审。Steps 用 checkbox 跟踪。

**Goal:** 把 vault 的 171 条评论信号投影进衡观 `CommentarySignal` 表，随每晚 run_sync 持续录入；政策链接用软引用，对未来「政策详情显示相关评论」前向兼容。Backend-only。

**Architecture:** 衡观加一张 `CommentarySignal` 表（一等实体 + `relatedPolicyPids` 软引用 Json）。pipeline `run_sync` 加第三个 collector（评论），复用既有 psycopg2 + savepoint + ON CONFLICT upsert 写法。无 FK 解析、不跳过悬挂边、单条失败不崩整批。

**Tech Stack:** Python3 + psycopg2（pipeline）；Prisma/Postgres（衡观）。

**Spec:** `docs/superpowers/specs/2026-06-08-commentary-projection-design.md`

---

## File Structure

| 文件 | 仓 | 责任 |
|---|---|---|
| `services/heng-guan/backend/prisma/schema.prisma` | 衡观 | +`CommentarySignal` model |
| `prisma/migrations/<ts>_commentary_signal/migration.sql` | 衡观 | 建表迁移 |
| `scripts/sync/pg_writer.py` | pipeline | +`build_commentary_upsert`（纯函数） |
| `scripts/sync/run_sync.py` | pipeline | +`collect_commentary_rows` + run() 集成 + build_summary 加计数 |
| `tests/sync/test_pg_writer.py` | pipeline | +upsert 测试 |
| `tests/sync/test_run_sync.py` | pipeline | +collect + 集成测试 |

---

## Task 1: 衡观 `CommentarySignal` 表 + 迁移（衡观仓 · Codex · [DB-MIGRATION]）

**Files:**
- Modify: `services/heng-guan/backend/prisma/schema.prisma`（末尾追加）
- Create: `services/heng-guan/backend/prisma/migrations/<ts>_commentary_signal/migration.sql`

从最新 `origin/master` 切分支 `feat/heng-commentary-signal`。

- [ ] **Step 1: schema 末尾追加 model**

```prisma
model CommentarySignal {
  id                String   @id @default(cuid())
  commentaryId      String   @unique
  title             String
  evidence          String?
  signalRole        String?
  confidence        Float?
  sourceAccount     String?
  businessTag       String?
  themeIds          Json?
  relatedPolicyPids Json?
  sourcePath        String?
  pipelineVersion   Int?
  syncedAt          DateTime?
  createdAt         DateTime @default(now())

  @@index([businessTag])
  @@index([signalRole])
}
```

- [ ] **Step 2: 生成迁移**

用本仓既有方式生成迁移（同 `20260608165000_l1_review_queue` 那样），迁移名 `commentary_signal`。迁移 SQL 应为 `CREATE TABLE "CommentarySignal" (...)` + 两个 `CREATE INDEX`，无外键（软引用）。

- [ ] **Step 3: 校验**

Run: `DATABASE_URL=<dev> npx prisma validate`
Expected: schema valid。`npm run build`（nest build）exit 0。

- [ ] **Step 4: Commit**

```bash
git add services/heng-guan/backend/prisma/schema.prisma services/heng-guan/backend/prisma/migrations/
git commit -m "feat(heng): CommentarySignal 表(评论信号投影·软引用关联政策)[DB-MIGRATION]"
```

> 审计后 Claude push + 开 PR 给 gloriahao0909。生产 db push 补这张表（与既有部署同法）。

---

## Task 2: `build_commentary_upsert`（pipeline · pg_writer · TDD）

**Files:**
- Modify: `scripts/sync/pg_writer.py`（在 `build_notification_insert` 后追加）
- Test: `tests/sync/test_pg_writer.py`

从 `main` 切分支 `feat/commentary-sync`。

- [ ] **Step 1: 写失败测试**

在 `tests/sync/test_pg_writer.py` 追加：

```python
def test_build_commentary_upsert():
    from scripts.sync import pg_writer
    row = {
        "commentary_id": "C_abc", "title": "标题", "evidence": "摘录",
        "signal_role": "risk", "confidence": 0.72, "source_account": "中电联",
        "business_tag": "power",
        "theme_ids": '["power_market"]',
        "related_policy_pids": '["P_2026_SC_x","P_missing"]',
        "source_path": "0_raw/commentaries/x.md", "pipeline_version": 1,
    }
    sql, params = pg_writer.build_commentary_upsert(row)
    assert 'INSERT INTO "CommentarySignal"' in sql
    assert 'ON CONFLICT ("commentaryId") DO UPDATE' in sql
    assert '%(theme_ids)s::jsonb' in sql
    assert '%(related_policy_pids)s::jsonb' in sql
    assert params["commentary_id"] == "C_abc"
    assert params["related_policy_pids"] == '["P_2026_SC_x","P_missing"]'  # 悬挂 pid 原样留
    assert params["business_tag"] == "power"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/sync/test_pg_writer.py::test_build_commentary_upsert -q`
Expected: FAIL（`AttributeError: ... build_commentary_upsert`）

- [ ] **Step 3: 实现**

在 `scripts/sync/pg_writer.py` 末尾追加：

```python
def build_commentary_upsert(row: dict) -> tuple[str, dict]:
    """INSERT ... ON CONFLICT (commentaryId) DO UPDATE。
    themeIds/relatedPolicyPids 为 JSON 字符串（::jsonb 转）；relatedPolicyPids 是软引用，
    悬挂 pid 原样存、不解析、不跳过。id=gen_random_uuid；createdAt/syncedAt=now。"""
    sql = '''
    INSERT INTO "CommentarySignal"
      ("id", "commentaryId", "title", "evidence", "signalRole", "confidence",
       "sourceAccount", "businessTag", "themeIds", "relatedPolicyPids",
       "sourcePath", "pipelineVersion", "syncedAt", "createdAt")
    VALUES
      (gen_random_uuid()::text, %(commentary_id)s, %(title)s, %(evidence)s,
       %(signal_role)s, %(confidence)s, %(source_account)s, %(business_tag)s,
       %(theme_ids)s::jsonb, %(related_policy_pids)s::jsonb,
       %(source_path)s, %(pipeline_version)s, now(), now())
    ON CONFLICT ("commentaryId") DO UPDATE SET
      "title"             = EXCLUDED."title",
      "evidence"          = EXCLUDED."evidence",
      "signalRole"        = EXCLUDED."signalRole",
      "confidence"        = EXCLUDED."confidence",
      "sourceAccount"     = EXCLUDED."sourceAccount",
      "businessTag"       = EXCLUDED."businessTag",
      "themeIds"          = EXCLUDED."themeIds",
      "relatedPolicyPids" = EXCLUDED."relatedPolicyPids",
      "sourcePath"        = EXCLUDED."sourcePath",
      "pipelineVersion"   = EXCLUDED."pipelineVersion",
      "syncedAt"          = now()
    '''
    params = {
        "commentary_id": row["commentary_id"],
        "title": row["title"],
        "evidence": row.get("evidence"),
        "signal_role": row.get("signal_role"),
        "confidence": row.get("confidence"),
        "source_account": row.get("source_account"),
        "business_tag": row.get("business_tag"),
        "theme_ids": row["theme_ids"],
        "related_policy_pids": row["related_policy_pids"],
        "source_path": row.get("source_path"),
        "pipeline_version": row["pipeline_version"],
    }
    return sql, params
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/sync/test_pg_writer.py::test_build_commentary_upsert -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/sync/pg_writer.py tests/sync/test_pg_writer.py
git commit -m "feat(sync): build_commentary_upsert(评论信号 upsert·软引用)"
```

---

## Task 3: `collect_commentary_rows`（pipeline · run_sync · TDD）

**Files:**
- Modify: `scripts/sync/run_sync.py`（加 import json + 新函数）
- Test: `tests/sync/test_run_sync.py`

- [ ] **Step 1: 写失败测试**

在 `tests/sync/test_run_sync.py` 追加：

```python
def test_collect_commentary_rows(tmp_path):
    import json
    from scripts.sync import run_sync as m
    d = tmp_path / "1_extracted"
    d.mkdir(parents=True)
    lines = [
        {"commentary_id": "C_1", "title": "T1", "evidence": "E1",
         "related_policy_ids": ["P_in", "P_missing"], "theme_ids": ["power_market"],
         "signal_role": "risk", "confidence": 0.7, "source_account": "中电联",
         "business_tag": "power", "path": "0_raw/commentaries/x.md"},
        {"title": "无id跳过", "related_policy_ids": []},  # 无 commentary_id → 跳过
    ]
    (d / "commentary_signals.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    rows = m.collect_commentary_rows(tmp_path, 1)
    assert len(rows) == 1
    r = rows[0]
    assert r["commentary_id"] == "C_1"
    assert json.loads(r["related_policy_pids"]) == ["P_in", "P_missing"]  # 悬挂原样
    assert json.loads(r["theme_ids"]) == ["power_market"]
    assert r["business_tag"] == "power"
    assert r["pipeline_version"] == 1

def test_collect_commentary_rows_absent_file(tmp_path):
    from scripts.sync import run_sync as m
    assert m.collect_commentary_rows(tmp_path, 1) == []  # 文件不存在→空
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/sync/test_run_sync.py::test_collect_commentary_rows -q`
Expected: FAIL（`AttributeError: ... collect_commentary_rows`）

- [ ] **Step 3: 实现**

确认 `scripts/sync/run_sync.py` 顶部已 `import json`（既有）。在 `collect_relation_rows` 后追加：

```python
def collect_commentary_rows(vault: Path, pipeline_version: int) -> list[dict]:
    rows = []
    fp = Path(vault) / "1_extracted" / "commentary_signals.jsonl"
    if not fp.exists():
        return rows
    for line in fp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        cid = d.get("commentary_id")
        if not cid:
            continue  # 无幂等键的跳过
        rows.append({
            "commentary_id": cid,
            "title": d.get("title") or "",
            "evidence": d.get("evidence"),
            "signal_role": d.get("signal_role"),
            "confidence": d.get("confidence"),
            "source_account": d.get("source_account"),
            "business_tag": d.get("business_tag") or None,
            # jsonb 字段序列化为 JSON 字符串；软引用：related 原样不解析
            "theme_ids": json.dumps(d.get("theme_ids") or [], ensure_ascii=False),
            "related_policy_pids": json.dumps(d.get("related_policy_ids") or [], ensure_ascii=False),
            "source_path": d.get("path") or d.get("sanitized_from"),
            "pipeline_version": pipeline_version,
        })
    return rows
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/sync/test_run_sync.py -k commentary_rows -q`
Expected: PASS（2 个用例）

- [ ] **Step 5: Commit**

```bash
git add scripts/sync/run_sync.py tests/sync/test_run_sync.py
git commit -m "feat(sync): collect_commentary_rows(读 commentary_signals.jsonl·软引用)"
```

---

## Task 4: run() 集成 + summary 计数（pipeline · run_sync · TDD）

**Files:**
- Modify: `scripts/sync/run_sync.py`（`run()` 加评论段；`build_summary` 加 `commentary` 参数）
- Test: `tests/sync/test_run_sync.py`

- [ ] **Step 1: 写失败测试**

在 `tests/sync/test_run_sync.py` 追加（mock 连接，断言评论段被调用且计数进 summary、单条失败被兜住）：

```python
def test_run_projects_commentary_and_counts(tmp_path, monkeypatch):
    import types, sys
    from scripts.sync import run_sync as m
    calls = {"commentary": 0}
    class FakeCur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return ("cuid1",)
    class FakeConn:
        def cursor(self): return FakeCur()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda _: FakeConn()))
    monkeypatch.setattr(m, "collect_policy_rows", lambda v, ver: ([], []))
    monkeypatch.setattr(m, "collect_relation_rows", lambda v, ver: [])
    monkeypatch.setattr(m, "collect_commentary_rows",
                        lambda v, ver: [{"commentary_id": "C_1"}, {"commentary_id": "C_2"}])
    def fake_upsert(row):
        calls["commentary"] += 1
        return "SQL", {"commentary_id": row["commentary_id"]}
    monkeypatch.setattr(m.pg_writer, "build_commentary_upsert", fake_upsert)
    monkeypatch.setattr(m.pg_writer, "execute_with_savepoint", lambda c, s, p: None)
    summary = m.run(tmp_path, tmp_path, 1, "postg:///x")
    assert calls["commentary"] == 2
    assert summary["commentary_count"] == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/sync/test_run_sync.py::test_run_projects_commentary_and_counts -q`
Expected: FAIL（`KeyError: 'commentary_count'` 或评论段未调用）

- [ ] **Step 3: 实现**

①改 `build_summary` 签名，加 `commentary` 参数并入 dict：

```python
def build_summary(synced: int, skipped_override: int, relations: int, errors: list[str],
                  skipped_invalid: int = 0, commentary: int = 0) -> dict:
    return {
        "synced_count": synced,
        "skipped_override_count": skipped_override,
        "relation_count": relations,
        "errors": errors,
        "skipped_invalid_count": skipped_invalid,
        "commentary_count": commentary,
    }
```

②在 `run()` 里，relation 投影循环之后、`conn.commit()` 之前（即现有 `rel_synced` 段后），加评论段：

```python
        commentary_rows = collect_commentary_rows(vault, pipeline_version)
        commentary_synced = 0
        for row in commentary_rows:
            try:
                sql, params = pg_writer.build_commentary_upsert(row)
                pg_writer.execute_with_savepoint(conn, sql, params)
                commentary_synced += 1
            except Exception as e:  # 单条失败不崩整批
                errors.append(f"commentary {row.get('commentary_id')}: {e}")
        conn.commit()
```

③把现有 `summary = build_summary(synced, 0, rel_synced, errors, skipped_invalid=len(skipped_rows))` 改为带 `commentary=commentary_synced`：

```python
    summary = build_summary(synced, 0, rel_synced, errors,
                            skipped_invalid=len(skipped_rows),
                            commentary=commentary_synced)
```

> 注：评论段在通知写消息段（`if errors:`）之前。评论 upsert 失败计入 errors，不影响政策/关系（各自 savepoint），与既有「单篇 policy 失败不崩整批」一致。

- [ ] **Step 4: 跑全 sync 测试确认通过**

Run: `python3 -m pytest tests/sync -q`
Expected: 全绿（含新增评论用例 + 既有 policy/relation/notification 无回归）

- [ ] **Step 5: principle_guard + Commit**

```bash
python3 -m scripts.audit.principle_guard scripts/sync   # exit 0
git add scripts/sync/run_sync.py tests/sync/test_run_sync.py
git commit -m "feat(sync): run_sync 集成评论投影段 + summary commentary_count"
```

> 审计后 Claude push + 开 pipeline PR + 合 main（随服务器 git pull + 镜像重建 + 每晚 cron 生效）。

---

## 部署（ops · Claude · 非本 plan 代码）

1. 衡观 PR（Task 1）合并 → 生产 `prisma db push` 补 `CommentarySignal` 表。
2. pipeline PR（Task 2-4）合 main → 服务器 `git fetch+reset` src + 镜像 rebuild。
3. 验证：生产 run_sync 一次 → `SELECT count(*) FROM "CommentarySignal"`（应 ~171）；抽查一条 `relatedPolicyPids` 含悬挂 pid 原样留存。
4. 每晚 cron 自动持续录入（env 已指生产）。

---

## Self-Review

**Spec coverage**：①CommentarySignal 表（Task 1 ✓ 字段全覆盖 spec §1）②run_sync 扩展 collect+upsert（Task 2/3 ✓）③run 集成+容错+计数（Task 4 ✓）④软引用不解析不跳过（Task 2/3 测试断言悬挂 pid 原样 ✓）⑤错误处理 per-row try/except（Task 4 ✓）。无遗漏。

**Placeholder scan**：无 TBD；每步含完整代码/命令/期望。

**Type consistency**：`build_commentary_upsert(row)` 的 params key（commentary_id/theme_ids/related_policy_pids…）与 `collect_commentary_rows` 产出的 row key 完全一致；`build_summary` 新增 `commentary` 参数在 Task 4 一处定义一处调用，键 `commentary_count` 一致。
