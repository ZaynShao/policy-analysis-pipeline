# B14 ⑦ L1 源质量池闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 L1 的 4 个源质量池(gate / checkpoint / sweep / fetch_fail)的「人判完 → 结论回灌 pipeline」这半闭环掉:人在衡观判,verdict 经标准信封回到 pipeline,交 applier 执行。

**Architecture:** 三段、三主。(1) **pipeline 侧 [B14·本 plan 建]**:标准信封 + `sync_l1_pool.py`(pool→衡观 PG)+ `poll_l1_verdicts.py`(PG verdict→pipeline,含重核/GC/删池行)+ seed fixtures;复用 `run_sync` 的 psycopg2 直写法但**不改** service-deploy 的 `run_sync`/`sync_tick`。(2) **衡观侧 [spec→前端团队]**:新表 `L1ReviewQueue` + NestJS 模块 + Vue 审核页 + DeepSeek 叙述 + MANAGER 门控。(3) **部署 [handoff→"知识库服务上云" session]**:迁移、服务器挂脚本、跨团队 PR、上线。

**Tech Stack:** Python 3 + psycopg2(pipeline 侧);Vue3/NestJS/Prisma/Postgres/DeepSeek(衡观侧,前端团队栈)。

**Decisions locked (2026-06-08):** 门控=MANAGER · 空池→我 seed 真 fixture · 部署/推 PR→上云 session。

**执行期修正(2026-06-08):** 本 repo 测试在顶层 `tests/`(pyproject `testpaths=["tests"]`),故测试路径用 `tests/l1_review_consumer/` 而非 `scripts/.../tests/`;模块码仍在 `scripts/l1_review_consumer/`。import 范本 = L1 的 `from scripts.l1_collect import review_pool as rp`。

**Owner tags:** `[B14]` 我本 session 建 · `[衡观-spec]` 出 spec 交前端团队 · `[部署-handoff]` 交上云 session · `[L1-dep]` 等 L1 交付。

---

## Part 0 — 标准信封契约(B14 owned · 跨池统一)`[B14]`

L1 OUT 记录:`{ref, kind, verdict, corrections?, reviewer, note, decided_run}`。B14 外包统一信封:

```json
{
  "envelope_v": 1,
  "pool": "l1_source_quality",
  "ref": "<channel|pid|url>",
  "kind": "gate|checkpoint|sweep|fetch_fail",
  "verdict": "<见 VERDICTS[kind]>",
  "corrections": { "corrected_label": "...", "retry_params": {...} },
  "reviewer": "<衡观 user id/name>",
  "note": "<人备注>",
  "decided_run": "<衡观侧批次/会话标识>",
  "decided_at": "<ISO8601, B14 补>",
  "idem_key": "<kind:ref:decided_run, B14 补>",
  "applied": false,
  "applied_at": null,
  "apply_result": null
}
```

落盘:`state/l1_review/verdicts.jsonl`(append;`applied` 由消费者回填)。

---

## Part 1 — pipeline 侧闭环代码 `[B14]` · 本 session 建 · worktree

### Task 0: 准备 worktree(拿到 L1 的 review_pool)

**Files:** 无新增,git 操作。

- [ ] **Step 1: 把 origin/main merge 进当前分支**(拿 `scripts/l1_collect/review_pool.py` + VERDICTS)

Run:
```bash
cd /Users/shaoziyuan/dev/政策分析-pipeline/.claude/worktrees/agitated-jennings-7c41f6
git fetch origin
git merge origin/main --no-edit
```
Expected: 干净 merge(本分支只多了 docs/ 下的 HTML,与 main 无冲突)。验证:
```bash
test -f scripts/l1_collect/review_pool.py && echo OK
python3 -c "from scripts.l1_collect.review_pool import VERDICTS; print(VERDICTS)"
```
Expected: 打印 4 个 kind 的裁决枚举。

- [ ] **Step 2: Commit(若 merge 产生 merge commit 已自动)**

### Task 1: 标准信封模块

**Files:**
- Create: `scripts/l1_review_consumer/__init__.py`(空)
- Create: `scripts/l1_review_consumer/envelope.py`
- Test: `scripts/l1_review_consumer/tests/test_envelope.py`

- [ ] **Step 1: 写失败测试**

```python
# scripts/l1_review_consumer/tests/test_envelope.py
from scripts.l1_review_consumer.envelope import wrap_verdict, ENVELOPE_V

def test_wrap_builds_idem_key_and_defaults():
    raw = {"ref": "swt.hebei.gov.cn", "kind": "fetch_fail", "verdict": "retry",
           "reviewer": "zayn", "note": "换 UA", "decided_run": "run42",
           "corrections": {"retry_params": {"ua": "mobile"}}}
    env = wrap_verdict(raw, decided_at="2026-06-08T10:00:00Z")
    assert env["envelope_v"] == ENVELOPE_V
    assert env["pool"] == "l1_source_quality"
    assert env["idem_key"] == "fetch_fail:swt.hebei.gov.cn:run42"
    assert env["applied"] is False and env["applied_at"] is None
    assert env["corrections"]["retry_params"]["ua"] == "mobile"

def test_wrap_rejects_bad_verdict():
    raw = {"ref": "x", "kind": "gate", "verdict": "nonsense",
           "reviewer": "z", "note": "", "decided_run": "r1"}
    try:
        wrap_verdict(raw, decided_at="2026-06-08T10:00:00Z")
        assert False, "should have raised"
    except ValueError as e:
        assert "verdict" in str(e)
```

- [ ] **Step 2: 运行验证失败**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_envelope.py -v`
Expected: FAIL(ModuleNotFoundError: envelope)

- [ ] **Step 3: 实现**

```python
# scripts/l1_review_consumer/envelope.py
"""B14 标准信封:把 L1 的 OUT 记录包成跨池统一格式。"""
from scripts.l1_collect.review_pool import VERDICTS

ENVELOPE_V = 1
POOL = "l1_source_quality"


def wrap_verdict(raw: dict, decided_at: str) -> dict:
    kind = raw["kind"]
    verdict = raw["verdict"]
    if kind not in VERDICTS:
        raise ValueError(f"unknown kind: {kind}")
    if verdict not in VERDICTS[kind]:
        raise ValueError(f"bad verdict {verdict!r} for kind {kind}; allowed={VERDICTS[kind]}")
    ref = raw["ref"]
    decided_run = raw.get("decided_run", "")
    return {
        "envelope_v": ENVELOPE_V,
        "pool": POOL,
        "ref": ref,
        "kind": kind,
        "verdict": verdict,
        "corrections": raw.get("corrections") or {},
        "reviewer": raw.get("reviewer", ""),
        "note": raw.get("note", ""),
        "decided_run": decided_run,
        "decided_at": decided_at,
        "idem_key": f"{kind}:{ref}:{decided_run}",
        "applied": False,
        "applied_at": None,
        "apply_result": None,
    }
```

- [ ] **Step 4: 运行验证通过**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_envelope.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_review_consumer/
git commit -m "feat(b14): L1 review verdict 标准信封 wrap_verdict + VERDICTS 校验"
```

### Task 2: seed 真 fixture(从 ferr.txt / checkpoint 抠真数据)

**Files:**
- Create: `scripts/l1_review_consumer/seed_fixtures.py`
- Test: `scripts/l1_review_consumer/tests/test_seed.py`

说明:pool 当前空,本 task 从 l1-repair worktree 的真实残留生成 fixture pool,供建/验/演示。**只读** ferr.txt / checkpoint 报告,写到一个独立 fixture pool 文件(不污染真 pool)。

- [ ] **Step 1: 写失败测试**

```python
# scripts/l1_review_consumer/tests/test_seed.py
from scripts.l1_review_consumer.seed_fixtures import fetch_fail_row

def test_fetch_fail_row_shape():
    row = fetch_fail_row(channel="河北省商务厅", domain="swt.hebei.gov.cn",
                         url="https://swt.hebei.gov.cn/zcfg/123.html", reason="body_too_short")
    assert row["kind"] == "fetch_fail"
    assert row["ref"] == "https://swt.hebei.gov.cn/zcfg/123.html"
    assert row["suggested_action"] in ("retry", "unfetchable", "drop")
    assert row["channel"] == "河北省商务厅"
    assert "swt.hebei" in row["evidence"]
```

- [ ] **Step 2: 运行验证失败**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_seed.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 + 执行生成真 fixture**

```python
# scripts/l1_review_consumer/seed_fixtures.py
"""从 L1 真实残留(ferr.txt / checkpoint 报告)生成 fixture pool 行。
执行期读 l1-repair worktree 的真文件;此处函数纯构造,便于测试。"""

def fetch_fail_row(channel: str, domain: str, url: str, reason: str) -> dict:
    return {"kind": "fetch_fail", "ref": url,
            "reason": reason, "suggested_action": "retry",
            "confidence": None, "evidence": f"{channel} {domain}"[:80],
            "channel": channel, "run_label": "seed_fixture"}

def checkpoint_row(domain: str, city: str, list_url: str) -> dict:
    return {"kind": "checkpoint", "ref": domain,
            "reason": "discovery_candidate_unverified", "suggested_action": "promote",
            "confidence": None, "evidence": f"{city} {list_url}"[:80],
            "channel": city, "run_label": "seed_fixture"}
```

执行期(EXECUTOR 跑,非测试):读 `/Users/shaoziyuan/dev/政策分析-pipeline-l1-repair/state/T1_incremental/quar/*ferr.txt` 真 URL + `state/l1_gate/discover_checkpoint_2026-06-08.html` 真候选,用上面函数构造行,经 `review_pool.append` 写到 `state/l1_review/pool.fixture.jsonl`。

- [ ] **Step 4: 运行验证通过**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_seed.py -v`
Expected: PASS

- [ ] **Step 5: 生成 fixture pool 并人工核对**

Run: `python3 -m scripts.l1_review_consumer.seed_fixtures --emit state/l1_review/pool.fixture.jsonl`
Expected: 写出 N 条(swt.hebei 的真 URL + checkpoint 真候选);`wc -l` 核对非空。

- [ ] **Step 6: Commit**(fixture 数据若 gitignore 则只 commit 代码)

```bash
git add scripts/l1_review_consumer/seed_fixtures.py scripts/l1_review_consumer/tests/test_seed.py
git commit -m "feat(b14): seed fixtures 从真实 ferr.txt/checkpoint 残留构造池行"
```

### Task 3: `sync_l1_pool.py` — pool → 衡观 PG(forward 传输)

**Files:**
- Create: `scripts/l1_review_consumer/sync_l1_pool.py`
- Test: `scripts/l1_review_consumer/tests/test_sync_rows.py`

说明:纯逻辑(pool 行 → PG upsert 行 dict)单测;真 PG 写入是 integration,标 `[部署-handoff]` 在有 DATABASE_URL 的环境跑。复用 `run_sync` 的 psycopg2 + ON CONFLICT 写法,**新脚本、不改 run_sync**。

- [ ] **Step 1: 写失败测试(纯映射逻辑)**

```python
# scripts/l1_review_consumer/tests/test_sync_rows.py
from scripts.l1_review_consumer.sync_l1_pool import pool_row_to_pg

def test_pool_row_to_pg_maps_fields():
    pool_row = {"kind": "fetch_fail", "ref": "https://swt.hebei.gov.cn/x.html",
                "reason": "body_too_short", "suggested_action": "retry",
                "confidence": None, "evidence": "河北省商务厅", "channel": "河北省商务厅",
                "run_label": "seed_fixture"}
    pg = pool_row_to_pg(pool_row)
    assert pg["pipelineKind"] == "fetch_fail"
    assert pg["pipelineRef"] == "https://swt.hebei.gov.cn/x.html"
    assert pg["dedupeKey"] == "fetch_fail::https://swt.hebei.gov.cn/x.html"
    assert pg["verdict"] is None          # 未判
    assert pg["suggestedAction"] == "retry"
```

- [ ] **Step 2: 运行验证失败**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_sync_rows.py -v`
Expected: FAIL

- [ ] **Step 3: 实现映射 + upsert SQL builder**

```python
# scripts/l1_review_consumer/sync_l1_pool.py
"""pool.jsonl → 衡观 PG L1ReviewQueue(forward)。新脚本,不改 service-deploy run_sync。"""
import json, os
from scripts.l1_collect.review_pool import load, POOL

TABLE = "L1ReviewQueue"

def pool_row_to_pg(r: dict) -> dict:
    return {
        "dedupeKey": f'{r["kind"]}::{r["ref"]}',
        "pipelineKind": r["kind"],
        "pipelineRef": r["ref"],
        "reason": r.get("reason"),
        "suggestedAction": r.get("suggested_action"),
        "confidence": r.get("confidence"),
        "evidence": r.get("evidence"),
        "channel": r.get("channel"),
        "runLabel": r.get("run_label"),
        "verdict": None,
    }

def build_upsert(row: dict):
    cols = list(row.keys())
    ph = ", ".join(["%s"] * len(cols))
    colnames = ", ".join(f'"{c}"' for c in cols)
    # 已判的行不覆盖 verdict;只在新插入时落待判项
    updates = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "verdict")
    sql = (f'INSERT INTO "{TABLE}" ({colnames}, "createdAt") VALUES ({ph}, now()) '
           f'ON CONFLICT ("dedupeKey") DO UPDATE SET {updates} '
           f'WHERE "{TABLE}"."verdict" IS NULL')
    return sql, [row[c] for c in cols]

def main(pool_path=POOL):
    import psycopg2
    rows = [pool_row_to_pg(r) for r in load(pool_path)]
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        for row in rows:
            sql, params = build_upsert(row)
            cur.execute("SAVEPOINT s"); 
            try:
                cur.execute(sql, params); cur.execute("RELEASE SAVEPOINT s")
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT s")
                print(f"skip {row['dedupeKey']}: {e}")
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: 运行验证通过**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_sync_rows.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_review_consumer/sync_l1_pool.py scripts/l1_review_consumer/tests/test_sync_rows.py
git commit -m "feat(b14): sync_l1_pool forward 映射 + ON CONFLICT upsert(不覆盖已判)"
```

### Task 4: `poll_l1_verdicts.py` — PG verdict → pipeline(reverse,含继承语义)

**Files:**
- Create: `scripts/l1_review_consumer/poll_l1_verdicts.py`
- Test: `scripts/l1_review_consumer/tests/test_poll.py`

继承语义守则:① 消费时**重核不盲信**(fetch_fail 判 retry → 实抓确认成功才记 drop 候选);② apply 成功后从 pool **删行**(无已解决态);③ `state/T1_incremental/review/` 暂存项消费后 GC。本 task 建「pool 删行 + 待回灌 verdict 落信封」核心逻辑,重核/GC 钩子留给 applier(L1)。

- [ ] **Step 1: 写失败测试(删池行 + 落信封)**

```python
# scripts/l1_review_consumer/tests/test_poll.py
import json
from pathlib import Path
from scripts.l1_review_consumer.poll_l1_verdicts import remove_from_pool, persist_envelope

def test_remove_from_pool_drops_matching_kind_ref(tmp_path):
    pool = tmp_path / "pool.jsonl"
    pool.write_text(
        json.dumps({"kind": "gate", "ref": "p1"}, ensure_ascii=False) + "\n" +
        json.dumps({"kind": "sweep", "ref": "p2"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    remove_from_pool(pool, kind="gate", ref="p1")
    left = [json.loads(l) for l in pool.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(left) == 1 and left[0]["ref"] == "p2"

def test_persist_envelope_appends(tmp_path):
    sink = tmp_path / "verdicts.jsonl"
    persist_envelope(sink, {"idem_key": "gate:p1:r1", "kind": "gate"})
    persist_envelope(sink, {"idem_key": "gate:p1:r1", "kind": "gate"})  # 幂等:同 idem_key 不重复
    rows = [json.loads(l) for l in sink.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
```

- [ ] **Step 2: 运行验证失败**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_poll.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# scripts/l1_review_consumer/poll_l1_verdicts.py
"""衡观 PG verdict → pipeline。reverse poll + 信封落盘 + 删池行(继承语义②)。
真 PG 读在 main();纯逻辑函数可单测。重核/GC 由 applier(L1)挂钩。"""
import json, os
from pathlib import Path
from scripts.l1_collect.review_pool import load as load_pool, POOL
from scripts.l1_review_consumer.envelope import wrap_verdict

def remove_from_pool(pool_path: Path, kind: str, ref: str) -> None:
    rows = [r for r in load_pool(pool_path) if (r.get("kind"), r.get("ref")) != (kind, ref)]
    pool_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

def persist_envelope(sink: Path, env: dict) -> bool:
    existing = set()
    if sink.exists():
        for l in sink.read_text(encoding="utf-8").splitlines():
            if l.strip():
                existing.add(json.loads(l).get("idem_key"))
    if env.get("idem_key") in existing:
        return False
    with open(sink, "a", encoding="utf-8") as f:
        f.write(json.dumps(env, ensure_ascii=False) + "\n")
    return True

def main():
    import psycopg2
    sink = Path(POOL).parent / "verdicts.jsonl"
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        cur.execute('SELECT "pipelineRef","pipelineKind","verdict","corrections",'
                    '"reviewer","note","runLabel","verdictAt" '
                    'FROM "L1ReviewQueue" WHERE "verdict" IS NOT NULL AND "syncedBack"=false')
        for ref, kind, verdict, corrections, reviewer, note, run_label, vat in cur.fetchall():
            raw = {"ref": ref, "kind": kind, "verdict": verdict,
                   "corrections": corrections, "reviewer": reviewer, "note": note,
                   "decided_run": run_label}
            env = wrap_verdict(raw, decided_at=(vat.isoformat() if vat else ""))
            if persist_envelope(sink, env):
                remove_from_pool(Path(POOL), kind, ref)   # 继承语义②:判完删池行
                cur.execute('UPDATE "L1ReviewQueue" SET "syncedBack"=true '
                            'WHERE "dedupeKey"=%s', (f"{kind}::{ref}",))
        conn.commit()
    finally:
        conn.close()
    print("verdicts → applier(L1):重核 + GC 在 applier 内,见 handoff")
```

- [ ] **Step 4: 运行验证通过**

Run: `python3 -m pytest scripts/l1_review_consumer/tests/test_poll.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/l1_review_consumer/poll_l1_verdicts.py scripts/l1_review_consumer/tests/test_poll.py
git commit -m "feat(b14): poll_l1_verdicts reverse + 信封落盘 + 判完删池行(继承语义②)"
```

### Task 5: applier handoff 文档(L1 地盘,我只定接口)

**Files:**
- Create: `docs/B14-applier-handoff-2026-06-08.md`

- [ ] **Step 1: 写 handoff**:消费者把 `state/l1_review/verdicts.jsonl`(标准信封)交 L1 applier;每 kind apply 见 L1 OUT 契约表;applier 必须:① 重核不盲信(fetch_fail 重抓确认);② 成功后回填 `applied/applied_at/apply_result`;③ GC `state/T1_incremental/review/`。过渡期沿用 `promote_checkpoint_channels.py` / `sweep_existing_commentary.py APPLY`。

- [ ] **Step 2: Commit**

```bash
git add docs/B14-applier-handoff-2026-06-08.md
git commit -m "docs(b14): applier handoff 接口契约(verdicts.jsonl → L1 per-kind apply)"
```

---

## Part 2 — 衡观审核页 `[衡观-spec]` · 出 spec 交前端团队

> 非本 session 写码;以下是给前端团队的精确实现 spec。照现成 PolicyDrawer(审核流)、Notification(新表)、DeepseekService(叙述)、VisitList(MANAGER 门控)模式。

**2.1 Prisma 新表**(`services/heng-guan/backend/prisma/schema.prisma`):
```prisma
enum L1ReviewKind { gate checkpoint sweep fetch_fail }

model L1ReviewQueue {
  id              String   @id @default(cuid())
  dedupeKey       String   @unique          // "{kind}::{ref}"
  pipelineKind    L1ReviewKind
  pipelineRef     String
  reason          String?
  suggestedAction String?
  confidence      Float?
  evidence        String?
  channel         String?
  runLabel        String?
  aiNarration     String?                    // DeepSeek 叙述
  aiNarratedAt    DateTime?
  verdict         String?                    // 人判;null=待判
  corrections     Json?
  reviewer        String?
  note            String?
  verdictAt       DateTime?
  syncedBack      Boolean  @default(false)   // poll 回灌后置 true
  createdAt       DateTime @default(now())
  @@index([verdict])
  @@index([pipelineKind])
}
```

**2.2 端点**(NestJS 模块 `l1-review`,JwtAuthGuard + 服务内 `req.user.role==='MANAGER'` 校验):
- `GET /l1-review?kind=&pending=true` — 列待判项(verdict IS NULL)
- `POST /l1-review/:id/narrate` — 调 DeepseekService 生成 `aiNarration`(温度 0.3,JSON mode);prompt:把该条讲成人话——这是什么(政策/渠道/URL)、为何进池(reason 字段含义)、人要判什么(列 VERDICTS 选项含义)。真证据(原标题/evidence)并列返回,不被叙述替代。
- `PATCH /l1-review/:id/verdict` — body `{verdict, note, corrections?}`;校验 verdict ∈ 该 kind 的 VERDICTS;写 `verdict/reviewer/note/verdictAt`。

**2.3 Vue 页**(`views/quality/L1ReviewQueue.vue` + `api/l1Review.ts` + router + nav,均 `role==='MANAGER'` 可见):卡片列每条;顶部 AI 叙述(人话)+ 下方真证据折叠;verdict 下拉(按 kind 给选项)+ note 输入 + 提交;提交后刷新。VERDICTS 映射前端常量与后端一致。

**2.4 VERDICTS(前后端共享常量,与 pipeline `review_pool.VERDICTS` 对齐)**:gate=pass/commentary/reject · checkpoint=promote/drop · sweep=confirm/keep · fetch_fail=retry/unfetchable/drop。

---

## Part 3 — 部署 `[部署-handoff]` · 交"知识库服务上云" session

> 前提确认 ✓(2026-06-08 用户确认):"知识库服务上云" session = 管 safety-platform 服务器部署 + pipeline→PG 同步的那条线。Part 3 handoff 甩它。

清单:
1. 应用 Prisma migration(`L1ReviewQueue` 表),staging 先行。
2. 把 `sync_l1_pool.py` / `poll_l1_verdicts.py` 挂上服务器:复用现有 `DATABASE_URL`/env;调度与 `sync_tick` **并行独立**(不改 run_sync/sync_tick);建议 forward 与 L1 采集同节奏、reverse 高频(分钟级)以使人判尽快回灌。
3. 跨团队 PR:Part 2 衡观代码 → PR 给 gloriahao0909(从 master 切,别推 master)。
4. 上线门:staging 验证 forward(seed fixture 进 PG)+ 人判 + reverse(verdict 回 `verdicts.jsonl` + 池删行)整链路通,再 prod。

---

## 协调依赖 `[L1-dep]`

1. **backfill 老残留进 pool**:把 `ferr.txt`(fetch_fail)、checkpoint 候选正式归集进 `state/l1_review/pool.jsonl`(L1 的 IN 活)。本 plan 的 seed fixture 仅供建/验,不代替全量 backfill。
2. **per-kind applier**:消费 `verdicts.jsonl`,按 OUT 契约表 apply;守重核 + GC + 回填 applied。过渡用现有 oneshots。

---

## Self-Review

- **Spec coverage**:信封(Part0/Task1)✓ · forward 传输(Task3)✓ · reverse + 继承语义②删池行(Task4)✓ · 空池 seed(Task2)✓ · 衡观页+表+叙述+MANAGER 门控(Part2)✓ · 部署/PR 交上云(Part3)✓ · L1 backfill/applier 依赖(协调)✓ · 继承语义①重核 + ③review GC → 落在 applier(Task5 handoff + 协调)✓。
- **类型一致**:`VERDICTS` 全程引用 `review_pool.VERDICTS`;`dedupeKey` 格式 `{kind}::{ref}` 在 Task3/Task4/Part2 一致;`idem_key` 格式 `{kind}:{ref}:{decided_run}` 在 envelope/poll 一致。
- **Owner 边界**:本 session 只建 Part 1(pipeline,我的仓)+ 出 Part 2/3 spec;不写衡观码、不推 PR、不碰 service-deploy 同步。
- **占位扫描**:无 TBD;handoff 部分是有意的跨线接口,非占位。
