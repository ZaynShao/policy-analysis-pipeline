# Plan A · Pipeline 服务层 实施计划

> **For agentic workers / Codex:** 按任务顺序 TDD 实施。每步 checkbox 跟踪。
> 配套 spec：`docs/superpowers/specs/2026-06-06-service-deploy-design.md`。
> 工作分支：`feat/service-deploy`（pipeline 仓）。本计划只在 pipeline 仓动代码。

**Goal:** 在 pipeline 仓建增量派生机器（hash ledger + l1_status 锁 + l2_queue 单 worker + L2 编排）和 sync 层（vault 派生产物 → heng-guan PostgreSQL），让"定期派生 + 推数据进前端 DB"可本地跑通、可测试。

**Architecture:** 新增两个独立 Python 包：`scripts/service/`（调度机器）与 `scripts/sync/`（DB 推送）。编排器用**注入式 stage 钩子**解耦——归属阶段调用现有 `scripts.l2_themescore.run_2b`（支持 `--pid-file` 逐篇增量），分析/结晶作为可注入钩子（Phase 1 不硬造增量-pairwise）。sync 层把映射逻辑（纯函数，重测）与 psycopg2 执行（薄封装）分离。

**Tech Stack:** Python 3、pytest（tmp_path 风格）、pyyaml、psycopg2-binary（新增依赖）、subprocess 调用现有阶段模块。

**纪律红线（AGENTS.md）:** 新代码源文件**零真实政策 PID 字面量**；测试只用合成示例 pid（如 `P_2024_NDRC_718`）；LLM 判定不写 raw；dry-run 优先。

---

## 文件结构

```
scripts/service/
├── __init__.py
├── hash_ledger.py     content-hash 增量账本（LedgerEntry / compute_hash / load / save / needs_rebuild / mark_done）
├── l1_status.py       L1 运行锁（L1Status / read_status / set_running / set_idle / is_running）
├── l2_queue.py        持久化优先级队列（QueueItem / enqueue / enqueue_batch / read_queue / next_item / mark_complete）
└── orchestrate.py     L2 编排（StageResult / process_pid / drain_queue + 真实 stage runner 工厂）

scripts/sync/
├── __init__.py
├── policy_mapper.py   business_view YAML → Policy 行 dict（纯函数）
├── relation_mapper.py relations JSONL → PolicySemanticRelation 行 dict（纯函数）
├── pg_writer.py       build_policy_upsert / build_relation_upsert（纯 SQL 构造）+ execute（薄 psycopg2 封装）
└── run_sync.py        入口：读 vault → map → upsert → 写 last_sync_run.json

tests/service/         test_hash_ledger / test_l1_status / test_l2_queue / test_orchestrate
tests/sync/            test_policy_mapper / test_relation_mapper / test_pg_writer
```

---

## Task 1: 加依赖 + 建包骨架

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/service/__init__.py`, `scripts/sync/__init__.py`
- Create: `tests/service/__init__.py`, `tests/sync/__init__.py`

- [ ] **Step 1: 加 psycopg2 依赖**

修改 `pyproject.toml` 的 dependencies：

```toml
dependencies = ["pyyaml", "anthropic>=0.40", "psycopg2-binary>=2.9"]
```

- [ ] **Step 2: 建空包文件**

```bash
mkdir -p scripts/service scripts/sync tests/service tests/sync
touch scripts/service/__init__.py scripts/sync/__init__.py tests/service/__init__.py tests/sync/__init__.py
```

- [ ] **Step 3: 装依赖验证**

Run: `pip3 install -e . && python3 -c "import psycopg2; print(psycopg2.__version__)"`
Expected: 打印版本号（如 `2.9.x`）

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml scripts/service/__init__.py scripts/sync/__init__.py tests/service/__init__.py tests/sync/__init__.py
git commit -m "chore(service): add psycopg2 dep + service/sync package skeletons"
```

---

## Task 2: hash_ledger.py（增量账本）

**Files:**
- Create: `scripts/service/hash_ledger.py`
- Test: `tests/service/test_hash_ledger.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/service/test_hash_ledger.py
from pathlib import Path
from scripts.service.hash_ledger import (
    LedgerEntry, compute_hash, load_ledger, save_ledger, needs_rebuild, mark_done,
)

def test_compute_hash_stable():
    assert compute_hash("内容A") == compute_hash("内容A")
    assert compute_hash("内容A") != compute_hash("内容B")

def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "ledger.json"
    entries = {"P_2024_NDRC_718": LedgerEntry("P_2024_NDRC_718", "abc", 1)}
    save_ledger(p, entries)
    loaded = load_ledger(p)
    assert loaded["P_2024_NDRC_718"].raw_content_hash == "abc"
    assert loaded["P_2024_NDRC_718"].pipeline_version == 1

def test_load_missing_returns_empty(tmp_path):
    assert load_ledger(tmp_path / "nope.json") == {}

def test_needs_rebuild_new_pid(tmp_path):
    assert needs_rebuild("P_NEW", "txt", 1, {}) is True

def test_needs_rebuild_hash_changed():
    led = {"P_X": LedgerEntry("P_X", compute_hash("old"), 1)}
    assert needs_rebuild("P_X", "new", 1, led) is True

def test_needs_rebuild_version_bumped():
    led = {"P_X": LedgerEntry("P_X", compute_hash("same"), 1)}
    assert needs_rebuild("P_X", "same", 2, led) is True

def test_needs_rebuild_unchanged():
    led = {"P_X": LedgerEntry("P_X", compute_hash("same"), 1)}
    assert needs_rebuild("P_X", "same", 1, led) is False

def test_mark_done_updates_entry():
    led = {}
    mark_done(led, "P_X", "txt", 3)
    assert led["P_X"].pipeline_version == 3
    assert led["P_X"].raw_content_hash == compute_hash("txt")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/service/test_hash_ledger.py -v`
Expected: FAIL（ModuleNotFoundError: scripts.service.hash_ledger）

- [ ] **Step 3: 写最小实现**

```python
# scripts/service/hash_ledger.py
"""Content-hash 增量账本。hash 或 pipeline_version 变化 → 需要重建。"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class LedgerEntry:
    pid: str
    raw_content_hash: str
    pipeline_version: int


def compute_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def load_ledger(path: Path) -> dict[str, LedgerEntry]:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {pid: LedgerEntry(**e) for pid, e in data.items()}


def save_ledger(path: Path, entries: dict[str, LedgerEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {pid: asdict(e) for pid, e in entries.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def needs_rebuild(pid: str, raw_text: str, current_version: int,
                  ledger: dict[str, LedgerEntry]) -> bool:
    entry = ledger.get(pid)
    if entry is None:
        return True
    if entry.pipeline_version != current_version:
        return True
    return entry.raw_content_hash != compute_hash(raw_text)


def mark_done(ledger: dict[str, LedgerEntry], pid: str, raw_text: str, version: int) -> None:
    ledger[pid] = LedgerEntry(pid, compute_hash(raw_text), version)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/service/test_hash_ledger.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/service/hash_ledger.py tests/service/test_hash_ledger.py
git commit -m "feat(service): content-hash incremental ledger"
```

---

## Task 3: l1_status.py（L1 运行锁）

**Files:**
- Create: `scripts/service/l1_status.py`
- Test: `tests/service/test_l1_status.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/service/test_l1_status.py
from scripts.service.l1_status import (
    L1Status, read_status, set_running, set_idle, is_running,
)

def test_read_missing_defaults_idle(tmp_path):
    st = read_status(tmp_path / "l1_status.json")
    assert st.status == "idle"
    assert st.pids_collected == []

def test_set_running_then_read(tmp_path):
    p = tmp_path / "l1_status.json"
    set_running(p, started_at="2026-06-06T09:00:00")
    st = read_status(p)
    assert st.status == "running"
    assert st.started_at == "2026-06-06T09:00:00"
    assert is_running(p) is True

def test_set_idle_records_pids(tmp_path):
    p = tmp_path / "l1_status.json"
    set_running(p, started_at="2026-06-06T09:00:00")
    set_idle(p, completed_at="2026-06-06T09:30:00", pids_collected=["P_A", "P_B"])
    st = read_status(p)
    assert st.status == "idle"
    assert st.completed_at == "2026-06-06T09:30:00"
    assert st.pids_collected == ["P_A", "P_B"]
    assert is_running(p) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/service/test_l1_status.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/service/l1_status.py
"""L1 运行锁。l1_status 是唯一的 L1 运行信号，不用进程存活判断。"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class L1Status:
    status: str = "idle"                     # "running" | "idle"
    started_at: str | None = None
    completed_at: str | None = None
    pids_collected: list[str] = field(default_factory=list)


def read_status(path: Path) -> L1Status:
    path = Path(path)
    if not path.exists():
        return L1Status()
    data = json.loads(path.read_text(encoding="utf-8"))
    return L1Status(**data)


def _write(path: Path, st: L1Status) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(st), ensure_ascii=False, indent=2), encoding="utf-8")


def set_running(path: Path, started_at: str) -> None:
    _write(path, L1Status(status="running", started_at=started_at))


def set_idle(path: Path, completed_at: str, pids_collected: list[str]) -> None:
    prev = read_status(path)
    _write(path, L1Status(status="idle", started_at=prev.started_at,
                          completed_at=completed_at, pids_collected=list(pids_collected)))


def is_running(path: Path) -> bool:
    return read_status(path).status == "running"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/service/test_l1_status.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/service/l1_status.py tests/service/test_l1_status.py
git commit -m "feat(service): l1_status run lock"
```

---

## Task 4: l2_queue.py（持久化优先级队列）

**Files:**
- Create: `scripts/service/l2_queue.py`
- Test: `tests/service/test_l2_queue.py`

队列语义：jsonl 持久化追加；`next_item` 先 high 后 normal，同优先级 FIFO；`enqueue` 按 pid 去重（已在队列则不重复加，若新条目是 high 而旧是 normal 则升级优先级）；`mark_complete` 移除该 pid（重写文件）。

- [ ] **Step 1: 写失败测试**

```python
# tests/service/test_l2_queue.py
from scripts.service.l2_queue import (
    QueueItem, enqueue, enqueue_batch, read_queue, next_item, mark_complete,
)

def test_enqueue_and_read(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "2026-06-06T09:00:00"))
    items = read_queue(p)
    assert len(items) == 1
    assert items[0].pid == "P_A"

def test_enqueue_dedup_same_pid(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_A", "cron", "normal", "t2"))
    assert len(read_queue(p)) == 1

def test_enqueue_upgrades_priority(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_A", "manual", "high", "t2"))
    items = read_queue(p)
    assert len(items) == 1
    assert items[0].priority == "high"
    assert items[0].trigger == "manual"

def test_next_item_high_before_normal(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_B", "manual", "high", "t2"))
    assert next_item(p).pid == "P_B"

def test_next_item_fifo_within_priority(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_B", "cron", "normal", "t2"))
    assert next_item(p).pid == "P_A"

def test_enqueue_batch(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue_batch(p, ["P_A", "P_B", "P_C"], "cron", "normal", "t1")
    assert len(read_queue(p)) == 3

def test_mark_complete_removes(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue_batch(p, ["P_A", "P_B"], "cron", "normal", "t1")
    mark_complete(p, "P_A")
    pids = [i.pid for i in read_queue(p)]
    assert pids == ["P_B"]

def test_next_item_empty_returns_none(tmp_path):
    assert next_item(tmp_path / "empty.jsonl") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/service/test_l2_queue.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/service/l2_queue.py
"""持久化优先级队列。手动(high)插队，cron(normal)批量；单 worker 串行消费。"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

_PRIORITY_RANK = {"high": 0, "normal": 1}


@dataclass
class QueueItem:
    pid: str
    trigger: str     # "manual" | "cron"
    priority: str    # "high" | "normal"
    requested_at: str


def read_queue(path: Path) -> list[QueueItem]:
    path = Path(path)
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(QueueItem(**json.loads(line)))
    return items


def _write_all(path: Path, items: list[QueueItem]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(i), ensure_ascii=False) for i in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def enqueue(path: Path, item: QueueItem) -> None:
    items = read_queue(path)
    for existing in items:
        if existing.pid == item.pid:
            # 去重；若新条目优先级更高则升级
            if _PRIORITY_RANK[item.priority] < _PRIORITY_RANK[existing.priority]:
                existing.priority = item.priority
                existing.trigger = item.trigger
                existing.requested_at = item.requested_at
                _write_all(path, items)
            return
    items.append(item)
    _write_all(path, items)


def enqueue_batch(path: Path, pids: list[str], trigger: str, priority: str,
                  requested_at: str) -> None:
    for pid in pids:
        enqueue(path, QueueItem(pid, trigger, priority, requested_at))


def next_item(path: Path) -> QueueItem | None:
    items = read_queue(path)
    if not items:
        return None
    # 稳定排序保 FIFO；按优先级 rank 取最高
    indexed = sorted(enumerate(items), key=lambda t: (_PRIORITY_RANK[t[1].priority], t[0]))
    return indexed[0][1]


def mark_complete(path: Path, pid: str) -> None:
    items = [i for i in read_queue(path) if i.pid != pid]
    _write_all(path, items)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/service/test_l2_queue.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/service/l2_queue.py tests/service/test_l2_queue.py
git commit -m "feat(service): persistent priority queue for L2 worker"
```

---

## Task 5: sync/policy_mapper.py（business_view → Policy 行，纯函数）

**Files:**
- Create: `scripts/sync/policy_mapper.py`
- Test: `tests/sync/test_policy_mapper.py`

映射契约见 spec §5.4。输入是 business_view YAML 已 parse 的 dict，输出是给 pg_writer 的行 dict。字段名对齐 §5.1：`pipeline_pid` / `pipeline_scores`(json) / `pipeline_themes`(json) / `pipeline_impact` / `importance`。重要性枚举映射：pipeline 的 1-5 整数分 → Prisma `PolicyImportance`（STRATEGIC/MAJOR/GENERAL/INFO）。

- [ ] **Step 1: 写失败测试**

```python
# tests/sync/test_policy_mapper.py
from scripts.sync.policy_mapper import map_business_view, importance_to_enum

def _bv():
    return {
        "pid": "P_2024_NDRC_718",
        "themes": ["power_market", "energy_storage_theme"],
        "primary_theme": "power_market",
        "重要性": 4,
        "scores": {"D1": 5, "D2": 4, "D3": 4, "D4": 4, "D5": 4, "D6": 5},
        "value_tags": ["机会"],
        "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c"},
        "comprehensive": True,
    }

def test_importance_to_enum_mapping():
    assert importance_to_enum(5) == "STRATEGIC"
    assert importance_to_enum(4) == "MAJOR"
    assert importance_to_enum(3) == "GENERAL"
    assert importance_to_enum(2) == "INFO"
    assert importance_to_enum(1) == "INFO"

def test_map_basic_fields():
    row = map_business_view(_bv(), pipeline_version=1)
    assert row["pipeline_pid"] == "P_2024_NDRC_718"
    assert row["importance"] == "MAJOR"
    assert row["pipeline_version"] == 1

def test_map_themes_is_json_serializable():
    import json
    row = map_business_view(_bv(), pipeline_version=1)
    themes = json.loads(row["pipeline_themes"])
    assert themes[0]["id"] == "power_market"
    assert themes[0]["isPrimary"] is True
    assert themes[1]["isPrimary"] is False

def test_map_scores_and_impact():
    import json
    row = map_business_view(_bv(), pipeline_version=1)
    assert json.loads(row["pipeline_scores"])["D1"] == 5
    assert "充电" in row["pipeline_impact"]

def test_map_comprehensive_flag_in_themes_meta():
    import json
    row = map_business_view(_bv(), pipeline_version=1)
    themes = json.loads(row["pipeline_themes"])
    assert any(t.get("isComprehensive") for t in themes) or row.get("comprehensive") is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/sync/test_policy_mapper.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/sync/policy_mapper.py
"""business_view YAML(dict) → Policy 行 dict。纯函数，映射契约见 spec §5.4。"""
from __future__ import annotations
import json


def importance_to_enum(score: int) -> str:
    """pipeline 1-5 分 → Prisma PolicyImportance。"""
    if score >= 5:
        return "STRATEGIC"
    if score == 4:
        return "MAJOR"
    if score == 3:
        return "GENERAL"
    return "INFO"


def map_business_view(bv: dict, pipeline_version: int) -> dict:
    primary = bv.get("primary_theme")
    comprehensive = bool(bv.get("comprehensive", False))
    themes = [
        {
            "id": t,
            "isPrimary": (t == primary),
            "isComprehensive": comprehensive and (t == primary),
        }
        for t in bv.get("themes", [])
    ]
    impact = bv.get("影响分析", {})
    impact_text = json.dumps(impact, ensure_ascii=False) if isinstance(impact, dict) else str(impact)
    return {
        "pipeline_pid": bv["pid"],
        "pipeline_version": pipeline_version,
        "importance": importance_to_enum(int(bv.get("重要性", 1))),
        "pipeline_scores": json.dumps(bv.get("scores", {}), ensure_ascii=False),
        "pipeline_themes": json.dumps(themes, ensure_ascii=False),
        "pipeline_impact": impact_text,
        "comprehensive": comprehensive,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/sync/test_policy_mapper.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/sync/policy_mapper.py tests/sync/test_policy_mapper.py
git commit -m "feat(sync): business_view -> Policy row mapper"
```

---

## Task 6: sync/relation_mapper.py（relations JSONL → 行,纯函数）

**Files:**
- Create: `scripts/sync/relation_mapper.py`
- Test: `tests/sync/test_relation_mapper.py`

输入是一条 relation 记录（已 parse 的 dict），输出 PolicySemanticRelation 行 dict。9 类关系类型透传。`from_pid`/`to_pid` 直接用 pipeline pid（pg_writer 负责把 pid 翻译成 CUID 外键，见 Task 7）。

- [ ] **Step 1: 写失败测试**

```python
# tests/sync/test_relation_mapper.py
from scripts.sync.relation_mapper import map_relation, VALID_RELATION_TYPES

def test_valid_types_count():
    assert len(VALID_RELATION_TYPES) == 9
    assert "derives_from" in VALID_RELATION_TYPES
    assert "conflicts_with" in VALID_RELATION_TYPES

def test_map_basic():
    rec = {
        "from_pid": "P_2024_NDRC_718",
        "to_pid": "P_2023_NDRC_100",
        "relation_type": "derives_from",
        "confidence": 0.9,
        "evidence": "为贯彻落实……",
    }
    row = map_relation(rec, pipeline_version=1)
    assert row["from_pid"] == "P_2024_NDRC_718"
    assert row["to_pid"] == "P_2023_NDRC_100"
    assert row["relation_type"] == "derives_from"
    assert row["confidence"] == 0.9
    assert row["pipeline_version"] == 1

def test_map_rejects_unknown_type():
    rec = {"from_pid": "P_A", "to_pid": "P_B", "relation_type": "bogus"}
    try:
        map_relation(rec, pipeline_version=1)
        assert False, "should raise"
    except ValueError:
        pass

def test_map_missing_confidence_ok():
    rec = {"from_pid": "P_A", "to_pid": "P_B", "relation_type": "references"}
    row = map_relation(rec, pipeline_version=1)
    assert row["confidence"] is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/sync/test_relation_mapper.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/sync/relation_mapper.py
"""relation 记录(dict) → PolicySemanticRelation 行 dict。纯函数。"""
from __future__ import annotations

VALID_RELATION_TYPES = (
    "derives_from", "extends", "iterates", "aligns_with", "cites_basis",
    "references", "clarifies", "supersedes", "conflicts_with",
)


def map_relation(rec: dict, pipeline_version: int) -> dict:
    rtype = rec.get("relation_type")
    if rtype not in VALID_RELATION_TYPES:
        raise ValueError(f"unknown relation_type: {rtype!r}")
    return {
        "from_pid": rec["from_pid"],
        "to_pid": rec["to_pid"],
        "relation_type": rtype,
        "confidence": rec.get("confidence"),
        "evidence": rec.get("evidence"),
        "pipeline_version": pipeline_version,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/sync/test_relation_mapper.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/sync/relation_mapper.py tests/sync/test_relation_mapper.py
git commit -m "feat(sync): relation record -> PolicySemanticRelation row mapper"
```

---

## Task 7: sync/pg_writer.py（SQL 构造纯函数 + psycopg2 薄执行）

**Files:**
- Create: `scripts/sync/pg_writer.py`
- Test: `tests/sync/test_pg_writer.py`

设计：把 **SQL 构造（纯字符串+参数,重测）** 与 **执行（薄 psycopg2 封装,集成测,无 DB 时 skip）** 分离。
- `build_policy_upsert(row) -> (sql, params)`：`INSERT ... ON CONFLICT (pipeline_pid) DO UPDATE`，**且 SET importance 只在 `importance_override IS NULL` 时生效**（spec §5.4 核心约束）。
- `build_relation_upsert(row, from_cuid, to_cuid) -> (sql, params)`：用 CUID 外键，`ON CONFLICT (from_policy_id, to_policy_id, relation_type) DO UPDATE`。
- `resolve_cuid(conn, pipeline_pid) -> str | None`：查 Policy.id by pipeline_pid。
- `execute(conn, sql, params)`：薄封装。

- [ ] **Step 1: 写失败测试（纯 SQL 构造部分）**

```python
# tests/sync/test_pg_writer.py
from scripts.sync.pg_writer import build_policy_upsert, build_relation_upsert

def test_policy_upsert_targets_pipeline_pid_conflict():
    row = {
        "pipeline_pid": "P_2024_NDRC_718", "pipeline_version": 1,
        "importance": "MAJOR", "pipeline_scores": "{}", "pipeline_themes": "[]",
        "pipeline_impact": "x", "comprehensive": True,
    }
    sql, params = build_policy_upsert(row)
    assert "ON CONFLICT" in sql
    assert "pipeline_pid" in sql or '"pipelinePid"' in sql
    assert "P_2024_NDRC_718" in params.values() if isinstance(params, dict) else "P_2024_NDRC_718" in params

def test_policy_upsert_respects_importance_override():
    """importance 字段只在 importanceOverride IS NULL 时更新——核心约束。"""
    row = {
        "pipeline_pid": "P_X", "pipeline_version": 1, "importance": "MAJOR",
        "pipeline_scores": "{}", "pipeline_themes": "[]", "pipeline_impact": "x",
        "comprehensive": False,
    }
    sql, _ = build_policy_upsert(row)
    # importance 的 DO UPDATE 子句必须带 override 守卫
    assert "importanceOverride" in sql or "importance_override" in sql
    assert "IS NULL" in sql

def test_relation_upsert_uses_cuid_fks():
    row = {
        "from_pid": "P_A", "to_pid": "P_B", "relation_type": "derives_from",
        "confidence": 0.9, "evidence": "e", "pipeline_version": 1,
    }
    sql, params = build_relation_upsert(row, from_cuid="cuid_a", to_cuid="cuid_b")
    assert "ON CONFLICT" in sql
    vals = list(params.values()) if isinstance(params, dict) else list(params)
    assert "cuid_a" in vals and "cuid_b" in vals
    assert "derives_from" in vals
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/sync/test_pg_writer.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/sync/pg_writer.py
"""PostgreSQL 写入。SQL 构造为纯函数（重测）；执行为薄 psycopg2 封装。

注意：列名用 Prisma 默认 camelCase（被 quote）。pipeline 只写 SQL，列名对齐
heng-guan Prisma schema（spec §5.1）。任一侧改动需同步 spec §5。
"""
from __future__ import annotations


def build_policy_upsert(row: dict) -> tuple[str, dict]:
    """INSERT ... ON CONFLICT (pipelinePid) DO UPDATE。
    importance 仅在 importanceOverride IS NULL 时更新（spec §5.4 核心约束）。"""
    sql = '''
    INSERT INTO "Policy"
      ("id", "pipelinePid", "pipelineVersion", "importance",
       "pipelineScores", "pipelineThemes", "pipelineImpact", "syncedAt")
    VALUES
      (gen_random_uuid()::text, %(pipeline_pid)s, %(pipeline_version)s,
       %(importance)s::"PolicyImportance",
       %(pipeline_scores)s::jsonb, %(pipeline_themes)s::jsonb,
       %(pipeline_impact)s, now())
    ON CONFLICT ("pipelinePid") DO UPDATE SET
      "pipelineVersion" = EXCLUDED."pipelineVersion",
      "pipelineScores"  = EXCLUDED."pipelineScores",
      "pipelineThemes"  = EXCLUDED."pipelineThemes",
      "pipelineImpact"  = EXCLUDED."pipelineImpact",
      "syncedAt"        = now(),
      "importance"      = CASE
        WHEN "Policy"."importanceOverride" IS NULL THEN EXCLUDED."importance"
        ELSE "Policy"."importance"
      END
    '''
    params = {
        "pipeline_pid": row["pipeline_pid"],
        "pipeline_version": row["pipeline_version"],
        "importance": row["importance"],
        "pipeline_scores": row["pipeline_scores"],
        "pipeline_themes": row["pipeline_themes"],
        "pipeline_impact": row["pipeline_impact"],
    }
    return sql, params


def build_relation_upsert(row: dict, from_cuid: str, to_cuid: str) -> tuple[str, dict]:
    sql = '''
    INSERT INTO "PolicySemanticRelation"
      ("id", "fromPolicyId", "toPolicyId", "relationType",
       "confidence", "evidence", "pipelineVersion", "createdAt")
    VALUES
      (gen_random_uuid()::text, %(from_cuid)s, %(to_cuid)s, %(relation_type)s,
       %(confidence)s, %(evidence)s, %(pipeline_version)s, now())
    ON CONFLICT ("fromPolicyId", "toPolicyId", "relationType") DO UPDATE SET
      "confidence" = EXCLUDED."confidence",
      "evidence"   = EXCLUDED."evidence",
      "pipelineVersion" = EXCLUDED."pipelineVersion"
    '''
    params = {
        "from_cuid": from_cuid,
        "to_cuid": to_cuid,
        "relation_type": row["relation_type"],
        "confidence": row["confidence"],
        "evidence": row.get("evidence"),
        "pipeline_version": row["pipeline_version"],
    }
    return sql, params


def resolve_cuid(conn, pipeline_pid: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute('SELECT "id" FROM "Policy" WHERE "pipelinePid" = %s', (pipeline_pid,))
        r = cur.fetchone()
        return r[0] if r else None


def execute(conn, sql: str, params) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)
```

> **注意（Codex 落地确认）:** `gen_random_uuid()` 需要 `pgcrypto` 扩展或 PG13+。若 heng-guan 用 CUID 而非 uuid，Policy 的 INSERT 分支（新政策从 sync 侧首次插入）可能极少触发——绝大多数政策由手动录入/L1 走 heng-guan 正常入库已存在，sync 主要走 UPDATE 分支。若新插入需要 CUID 兼容，改用 heng-guan 提供的 id 生成方式或让 sync 只 UPDATE 已存在记录（见 run_sync Task 8 的策略开关）。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/sync/test_pg_writer.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/sync/pg_writer.py tests/sync/test_pg_writer.py
git commit -m "feat(sync): pg upsert SQL builders with importance-override guard"
```

---

## Task 8: sync/run_sync.py（入口：读 vault → upsert → 写 last_sync_run.json）

**Files:**
- Create: `scripts/sync/run_sync.py`
- Test: `tests/sync/test_run_sync.py`

入口职责：遍历 vault `_meta/business_view/*.yaml` → map → 收集行；遍历 `1_extracted/relations/*.jsonl` → map → 收集行；连 DB upsert；写 `state/last_sync_run.json {synced_count, skipped_override_count, relation_count, errors[]}`。
为可测：把"收集行"逻辑（纯,读文件→行 list）与"执行 upsert"（需 DB）分离。测试只测收集逻辑 + summary 构造，DB 执行集成测无 DB 时 skip。

- [ ] **Step 1: 写失败测试**

```python
# tests/sync/test_run_sync.py
from pathlib import Path
import json
from scripts.sync.run_sync import collect_policy_rows, collect_relation_rows, build_summary

def _write_bv(vault: Path, pid: str):
    d = vault / "_meta" / "business_view"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.yaml").write_text(
        f"pid: {pid}\nthemes: [power_market]\nprimary_theme: power_market\n"
        f"重要性: 4\nscores: {{D1: 5, D2: 4, D3: 4, D4: 4, D5: 4, D6: 5}}\n"
        f"value_tags: [机会]\n影响分析: {{加油: a, 充电: b, 电力_储能_V2G_交易: c}}\n"
        f"comprehensive: false\n", encoding="utf-8")

def test_collect_policy_rows(tmp_path):
    _write_bv(tmp_path, "P_2024_NDRC_718")
    rows = collect_policy_rows(tmp_path, pipeline_version=1)
    assert len(rows) == 1
    assert rows[0]["pipeline_pid"] == "P_2024_NDRC_718"
    assert rows[0]["importance"] == "MAJOR"

def test_collect_policy_rows_empty(tmp_path):
    assert collect_policy_rows(tmp_path, pipeline_version=1) == []

def test_collect_relation_rows(tmp_path):
    d = tmp_path / "1_extracted" / "relations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "derives_from.jsonl").write_text(
        json.dumps({"from_pid": "P_A", "to_pid": "P_B",
                    "relation_type": "derives_from", "confidence": 0.9}) + "\n",
        encoding="utf-8")
    rows = collect_relation_rows(tmp_path, pipeline_version=1)
    assert len(rows) == 1
    assert rows[0]["relation_type"] == "derives_from"

def test_build_summary():
    s = build_summary(synced=10, skipped_override=2, relations=5, errors=["e1"])
    assert s["synced_count"] == 10
    assert s["skipped_override_count"] == 2
    assert s["relation_count"] == 5
    assert s["errors"] == ["e1"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/sync/test_run_sync.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/sync/run_sync.py
"""Sync 入口：vault 派生产物 → heng-guan PostgreSQL upsert。

只 upsert，不删除；不碰 pipelinePid IS NULL 的手动录入记录（靠 ON CONFLICT 语义）。
importance 不踩人工 override（SQL CASE 守卫，见 pg_writer）。
"""
from __future__ import annotations
import argparse
import glob
import json
import os
from pathlib import Path

import yaml

from scripts.sync.policy_mapper import map_business_view
from scripts.sync.relation_mapper import map_relation
from scripts.sync import pg_writer


def collect_policy_rows(vault: Path, pipeline_version: int) -> list[dict]:
    rows = []
    for fp in sorted(glob.glob(str(Path(vault) / "_meta" / "business_view" / "*.yaml"))):
        bv = yaml.safe_load(Path(fp).read_text(encoding="utf-8"))
        if bv and bv.get("pid"):
            rows.append(map_business_view(bv, pipeline_version))
    return rows


def collect_relation_rows(vault: Path, pipeline_version: int) -> list[dict]:
    rows = []
    rel_dir = Path(vault) / "1_extracted" / "relations"
    for fp in sorted(glob.glob(str(rel_dir / "*.jsonl"))):
        for line in Path(fp).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("from_pid") and rec.get("to_pid") and rec.get("relation_type"):
                try:
                    rows.append(map_relation(rec, pipeline_version))
                except ValueError:
                    continue  # 未知关系类型跳过（不污染 DB）
    return rows


def build_summary(synced: int, skipped_override: int, relations: int, errors: list[str]) -> dict:
    return {
        "synced_count": synced,
        "skipped_override_count": skipped_override,
        "relation_count": relations,
        "errors": errors,
    }


def run(vault: Path, state_dir: Path, pipeline_version: int, database_url: str) -> dict:
    import psycopg2
    policy_rows = collect_policy_rows(vault, pipeline_version)
    relation_rows = collect_relation_rows(vault, pipeline_version)
    errors: list[str] = []
    synced = 0
    conn = psycopg2.connect(database_url)
    try:
        for row in policy_rows:
            try:
                sql, params = pg_writer.build_policy_upsert(row)
                pg_writer.execute(conn, sql, params)
                synced += 1
            except Exception as e:  # 单篇失败不崩整批
                errors.append(f"policy {row.get('pipeline_pid')}: {e}")
        rel_synced = 0
        for row in relation_rows:
            from_cuid = pg_writer.resolve_cuid(conn, row["from_pid"])
            to_cuid = pg_writer.resolve_cuid(conn, row["to_pid"])
            if not from_cuid or not to_cuid:
                continue  # 关系两端必须已存在为 Policy
            try:
                sql, params = pg_writer.build_relation_upsert(row, from_cuid, to_cuid)
                pg_writer.execute(conn, sql, params)
                rel_synced += 1
            except Exception as e:
                errors.append(f"relation {row['from_pid']}->{row['to_pid']}: {e}")
        conn.commit()
    finally:
        conn.close()
    summary = build_summary(synced, 0, rel_synced, errors)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "last_sync_run.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--pipeline-version", type=int, default=1)
    args = ap.parse_args(argv)
    database_url = os.environ["DATABASE_URL"]
    summary = run(Path(args.vault), Path(args.state_dir), args.pipeline_version, database_url)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/sync/test_run_sync.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/sync/run_sync.py tests/sync/test_run_sync.py
git commit -m "feat(sync): run_sync entry collecting vault rows + upsert + summary"
```

---

## Task 9: service/orchestrate.py（L2 编排，注入式 stage 钩子）

**Files:**
- Create: `scripts/service/orchestrate.py`
- Test: `tests/service/test_orchestrate.py`

编排职责（spec §4）：从 l2_queue 取 pid（优先级序）→ 查 hash_ledger 是否需重建 → 调**归属**（注入式 runner，真实实现为 subprocess 调 `run_2b apply --pid-file`）→ 调**结晶/分析**（注入式可选钩子，Phase 1 默认 no-op）→ `mark_done` + `mark_complete` → 队列空后触发 **sync**（注入式）。
用注入式 runner 让单测不依赖真实 LLM/subprocess/DB。

- [ ] **Step 1: 写失败测试**

```python
# tests/service/test_orchestrate.py
from pathlib import Path
from scripts.service.hash_ledger import LedgerEntry, compute_hash
from scripts.service.l2_queue import QueueItem, enqueue
from scripts.service.orchestrate import StageResult, process_pid, drain_queue

def test_process_pid_skips_when_unchanged():
    ledger = {"P_X": LedgerEntry("P_X", compute_hash("same"), 1)}
    calls = []
    res = process_pid("P_X", "same", version=1, ledger=ledger,
                      run_attribution=lambda pid: calls.append(pid))
    assert res.ok is True
    assert res.error == "skipped"
    assert calls == []  # 未变 → 不调归属

def test_process_pid_runs_when_changed():
    ledger = {}
    calls = []
    res = process_pid("P_X", "new", version=1, ledger=ledger,
                      run_attribution=lambda pid: calls.append(pid))
    assert res.ok is True
    assert calls == ["P_X"]
    assert "P_X" in ledger  # mark_done 已更新账本

def test_process_pid_records_error():
    def boom(pid):
        raise RuntimeError("llm failed")
    res = process_pid("P_X", "txt", version=1, ledger={},
                      run_attribution=boom)
    assert res.ok is False
    assert "llm failed" in res.error

def test_drain_queue_processes_high_first(tmp_path):
    q = tmp_path / "q.jsonl"
    enqueue(q, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(q, QueueItem("P_B", "manual", "high", "t2"))
    order = []
    sync_calls = []
    drain_queue(
        queue_path=q,
        ledger={},
        ledger_path=tmp_path / "ledger.json",
        raw_text_for=lambda pid: pid + "_txt",
        version=1,
        run_attribution=lambda pid: order.append(pid),
        run_sync=lambda: sync_calls.append("synced"),
    )
    assert order[0] == "P_B"   # high 先
    assert order == ["P_B", "P_A"]
    assert sync_calls == ["synced"]   # 队列排空后触发一次 sync

def test_drain_queue_empty_no_sync(tmp_path):
    q = tmp_path / "q.jsonl"
    sync_calls = []
    drain_queue(queue_path=q, ledger={}, ledger_path=tmp_path / "l.json",
                raw_text_for=lambda pid: "", version=1,
                run_attribution=lambda pid: None,
                run_sync=lambda: sync_calls.append("x"))
    assert sync_calls == []  # 空队列不触发 sync
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/service/test_orchestrate.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写最小实现**

```python
# scripts/service/orchestrate.py
"""L2 编排器。队列取 pid → 归属增量 → [结晶/分析钩子] → 账本 → 排空后 sync。

stage runner 注入式，便于测试。真实 runner（subprocess 调 run_2b）由工厂构造。
分析(语义关系)是 pairwise 全量、③-C 未 apply（spec P3）→ Phase 1 默认 no-op 钩子，
不在此硬造增量-pairwise 机制。
"""
from __future__ import annotations
import subprocess
import tempfile
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from scripts.service.hash_ledger import (
    LedgerEntry, needs_rebuild, mark_done, save_ledger,
)
from scripts.service import l2_queue


@dataclass
class StageResult:
    pid: str
    ok: bool
    error: str | None = None


def process_pid(pid: str, raw_text: str, version: int,
                ledger: dict[str, LedgerEntry],
                run_attribution: Callable[[str], None],
                run_crystallize: Callable[[str], None] | None = None) -> StageResult:
    if not needs_rebuild(pid, raw_text, version, ledger):
        return StageResult(pid, True, "skipped")
    try:
        run_attribution(pid)
        if run_crystallize is not None:
            run_crystallize(pid)
    except Exception as e:
        return StageResult(pid, False, str(e))
    mark_done(ledger, pid, raw_text, version)
    return StageResult(pid, True, None)


def drain_queue(queue_path: Path, ledger: dict, ledger_path: Path,
                raw_text_for: Callable[[str], str], version: int,
                run_attribution: Callable[[str], None],
                run_sync: Callable[[], None],
                run_crystallize: Callable[[str], None] | None = None) -> list[StageResult]:
    results: list[StageResult] = []
    processed_any = False
    while True:
        item = l2_queue.next_item(queue_path)
        if item is None:
            break
        res = process_pid(item.pid, raw_text_for(item.pid), version, ledger,
                          run_attribution, run_crystallize)
        results.append(res)
        l2_queue.mark_complete(queue_path, item.pid)
        save_ledger(ledger_path, ledger)
        processed_any = True
    if processed_any:
        run_sync()
    return results


# ---- 真实 stage runner 工厂（生产用，单测不覆盖 subprocess 本体）----

def make_attribution_runner(vault: str, state: str, gen_model: str, judge_model: str,
                            gen_provider: str = "anthropic",
                            judge_provider: str = "openai") -> Callable[[str], None]:
    """逐篇调 run_2b apply --pid-file（run_2b 已支持 --pid-file 限定 pid）。"""
    def run(pid: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump([pid], f)
            pid_file = f.name
        cmd = [
            "python3", "-m", "scripts.l2_themescore.run_2b", "apply",
            "--vault", vault, "--state", state, "--pid-file", pid_file,
            "--gen-model", gen_model, "--gen-provider", gen_provider,
            "--judge-model", judge_model, "--judge-provider", judge_provider,
        ]
        subprocess.run(cmd, check=True)
    return run
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/service/test_orchestrate.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/service/orchestrate.py tests/service/test_orchestrate.py
git commit -m "feat(service): L2 orchestrator with injectable stage hooks"
```

---

## Task 10: principle_guard 守卫 + 全量测试 + 集成冒烟说明

**Files:**
- Test: 全 service/sync 测试
- 验证: `scripts/audit/principle_guard.py`（现有，AGENTS.md 红线工具）

- [ ] **Step 1: 跑 principle_guard 确认零 PID 字面量**

Run: `python3 -m scripts.audit.principle_guard scripts/service && python3 -m scripts.audit.principle_guard scripts/sync`
Expected: 通过（源码无真实政策 PID 字面量）。
若工具只接受单路径，分别跑两次。若报出测试里的 `P_2024_NDRC_718` —— 那是 tests/ 下的合成示例，确认 guard 只扫 scripts/ 不扫 tests/；如扫到 scripts/，检查是否误留 pid 字面量并移除。

- [ ] **Step 2: 跑全量新测试**

Run: `pytest tests/service tests/sync -v`
Expected: PASS（全绿，约 38 项）

- [ ] **Step 3: 跑全仓回归确认没碰坏现有测试**

Run: `pytest -q`
Expected: PASS（含现有 242+ 测试，无新增失败）

- [ ] **Step 4: 写集成冒烟手册（不跑真实 DB/LLM）**

Create: `scripts/service/README.md`

```markdown
# Pipeline 服务层

增量派生机器 + sync 层。详见 spec `docs/superpowers/specs/2026-06-06-service-deploy-design.md`。

## 组件
- `hash_ledger` 增量账本（content-hash + pipeline_version）
- `l1_status` L1 运行锁（唯一运行信号，不用进程存活判断）
- `l2_queue` 持久化优先级队列（manual=high 插队，cron=normal 批量）
- `orchestrate` L2 编排（队列→归属增量→[结晶/分析钩子]→账本→排空后 sync）
- `../sync/run_sync` vault 派生产物 → heng-guan PostgreSQL upsert

## 本地集成冒烟（需本地 Postgres + 已 apply heng-guan schema 迁移）
\`\`\`bash
set -a; . ~/.config/policy-pipeline/models.env; set +a
DATABASE_URL=postgres://localhost/heng_dev \
  python3 -m scripts.sync.run_sync \
  --vault "/path/to/vault" --state-dir state/service --pipeline-version 1
cat state/service/last_sync_run.json
\`\`\`

## 关键纪律
- sync 只 upsert，不删除；不碰 pipelinePid IS NULL 的手动录入记录。
- importance 不踩人工 override（SQL CASE 守卫）。
- 分析(语义关系)Phase 1 不增量；①-C apply 后再设计增量-pairwise。
- 列名对齐 heng-guan Prisma schema（spec §5.1），任一侧改动同步 spec §5。
```

- [ ] **Step 5: Commit**

```bash
git add scripts/service/README.md
git commit -m "docs(service): integration smoke guide + principle_guard verified"
```

---

## Self-Review（已对 spec 核对）

**Spec 覆盖：**
- §3 目录/state 文件 → hash_ledger/l1_status/l2_queue/last_sync_run 全部落地 ✓
- §4.1 增量(content-hash + version) → Task 2 ✓
- §4.2 L2 单次触发 → 由 systemd ExecStartPost 触发（Plan C），编排器消费整批队列 ✓
- §4.3 单 worker 队列 + 优先级插队 → Task 4 + Task 9 ✓
- §4.4 L1 不重叠 → l1_status 锁（Task 3）+ systemd 单例（Plan C）✓
- §5.4 字段映射 + importance override 守卫 → Task 5/7 ✓
- §6 sync 层（mapper + pg_writer + run_sync）→ Task 5-8 ✓
- §6 只 upsert 不删除、不碰手动录入 → run_sync 用 ON CONFLICT + resolve_cuid ✓

**已知 scope 边界（非 gap，spec 已声明）：**
- 分析(语义关系)增量 → Phase 1 不做（③-C 未 apply，P3）。编排器留可注入钩子。
- 结晶具体实现 → 注入式钩子，Phase 1 默认 no-op；前端消费基础数据为本阶段 bar（spec §9 Phase 2 才做主题聚类视图）。
- L1 编排（manual-entry 触发逐篇）→ 由 Plan B 的 NestJS 端点写 l2_queue（high），本计划提供队列接口。

**类型一致性核对：** LedgerEntry/QueueItem/StageResult/L1Status 字段在各 task 引用一致；map_business_view 输出键（pipeline_pid/pipeline_scores/...）与 pg_writer 入参键一致；relation row 键（from_pid/to_pid/relation_type/confidence/evidence/pipeline_version）跨 Task 6/7/8 一致。
