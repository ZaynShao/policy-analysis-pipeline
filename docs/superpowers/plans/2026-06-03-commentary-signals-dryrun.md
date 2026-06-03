# Commentary Signals Dry-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic dry-run that turns already-linked raw commentaries into internal calibration signals without writing the vault.

**Architecture:** Read `0_raw/commentaries/*.md`, parse frontmatter, emit one signal per commentary with non-empty `related_policy`, and write machine-readable state plus a Chinese HTML report under the engineering repo. The first loop is conservative: no LLM calls, no raw edits, and no public-facing claim that conclusions are produced from external opinions.

**Tech Stack:** Python 3, PyYAML, pytest, existing vault schema and theme registry.

---

### Task 1: Parser And Extractor Tests

**Files:**
- Create: `tests/commentary_signals/test_extractor.py`
- Create: `scripts/commentary_signals/__init__.py`
- Create: `scripts/commentary_signals/extractor.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from scripts.commentary_signals.extractor import (
    commentary_id,
    extract_commentary_signal,
    parse_markdown,
)


def test_parse_markdown_reads_frontmatter_and_body(tmp_path):
    path = tmp_path / "评论.md"
    path.write_text("---\ntitle: 电价改革解读\nrelated_policy:\n  - P_2025_NDRC_136\n---\n正文", encoding="utf-8")

    doc = parse_markdown(path, tmp_path)

    assert doc.frontmatter["title"] == "电价改革解读"
    assert doc.body == "正文"


def test_commentary_id_is_path_stable(tmp_path):
    path = tmp_path / "a.md"
    assert commentary_id(path, tmp_path) == commentary_id(path, tmp_path)


def test_extract_commentary_signal_for_linked_commentary(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\ntitle: 136号文短期风险\nrelated_policy:\n  - P_2025_NDRC_136\nbusiness_tag: power\n---\n短期收益不确定性上升,但长期市场化机会明确。", encoding="utf-8")
    doc = parse_markdown(path, tmp_path)

    signal = extract_commentary_signal(doc, {"power_market": ["电力市场", "电价", "市场化"]})

    assert signal is not None
    assert signal.related_policy_ids == ["P_2025_NDRC_136"]
    assert signal.signal_role == "risk"
    assert signal.theme_ids == ["power_market"]
    assert "不确定性" in signal.evidence


def test_unlinked_commentary_returns_no_signal(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\ntitle: 行业新闻\n---\n正文", encoding="utf-8")
    doc = parse_markdown(path, tmp_path)

    assert extract_commentary_signal(doc, {}) is None
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/commentary_signals/test_extractor.py`

Expected: FAIL because `scripts.commentary_signals` does not exist.

- [ ] **Step 3: Implement minimal parser and extractor**

Implement:
- frontmatter split on leading `---`
- stable `C_` id from relative path SHA-256
- `related_policy` normalization from string or list
- signal role keyword priority: risk, opportunity, execution, attention, interpretation
- theme matching by registry aliases in title/body
- short evidence excerpt around the first matched keyword

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/commentary_signals/test_extractor.py`

Expected: PASS.

### Task 2: Dry-Run Runner And Report

**Files:**
- Create: `tests/commentary_signals/test_run.py`
- Create: `scripts/commentary_signals/report.py`
- Create: `scripts/commentary_signals/run.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from pathlib import Path

from scripts.commentary_signals.run import run_dryrun


def test_dryrun_writes_signals_review_queue_summary_and_html(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    com = vault / "0_raw" / "commentaries"
    reg = vault / "_meta"
    com.mkdir(parents=True)
    reg.mkdir(parents=True)
    (reg / "themes_registry.yaml").write_text(
        "themes:\n  - id: power_market\n    zh: 电力市场\n    aliases: [电力市场, 市场化, 电价]\n",
        encoding="utf-8",
    )
    (com / "评论.md").write_text(
        "---\ntitle: 电价市场化风险\nrelated_policy: [P_2025_NDRC_136]\n---\n短期收益不确定性上升。",
        encoding="utf-8",
    )

    result = run_dryrun(vault, state)

    assert result["summary"]["emitted_signals"] == 1
    assert (state / "signals.jsonl").exists()
    assert (state / "review_queue.jsonl").exists()
    assert (state / "summary.json").exists()
    assert (state / "reports" / "commentary_signals_dryrun.html").exists()
    row = json.loads((state / "signals.jsonl").read_text(encoding="utf-8").strip())
    assert row["signal_role"] == "risk"
    html = (state / "reports" / "commentary_signals_dryrun.html").read_text(encoding="utf-8")
    assert "评论校准信号 dry-run" in html
    assert "内部校准" in html


def test_dryrun_does_not_modify_commentary(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    com = vault / "0_raw" / "commentaries"
    reg = vault / "_meta"
    com.mkdir(parents=True)
    reg.mkdir(parents=True)
    (reg / "themes_registry.yaml").write_text("themes: []\n", encoding="utf-8")
    path = com / "评论.md"
    path.write_text("---\ntitle: 无关联\n---\n正文", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    run_dryrun(vault, state)

    assert path.read_text(encoding="utf-8") == before
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/commentary_signals/test_run.py`

Expected: FAIL because `run_dryrun` does not exist.

- [ ] **Step 3: Implement runner and HTML report**

Implement:
- `run_dryrun(vault, state)` writes `signals.jsonl`, `review_queue.jsonl`, `summary.json`, and `reports/commentary_signals_dryrun.html`
- skip unlinked commentaries and `not_policy_related`
- review queue rows for linked commentaries with no theme hit
- report explains this is internal calibration/audit, not direct consumer-facing evidence injection

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/commentary_signals`

Expected: PASS.

### Task 3: Live Dry-Run And Verification

**Files:**
- Create: `state/commentary_signals/dryrun_20260603/signals.jsonl`
- Create: `state/commentary_signals/dryrun_20260603/review_queue.jsonl`
- Create: `state/commentary_signals/dryrun_20260603/summary.json`
- Create: `state/commentary_signals/dryrun_20260603/reports/commentary_signals_dryrun.html`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Run live dry-run**

Run:

```bash
python3 -m scripts.commentary_signals.run dry-run \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state state/commentary_signals/dryrun_20260603
```

Expected: writes only engineering repo state; vault git status remains clean.

- [ ] **Step 2: Run verification**

Run:

```bash
python3 -m pytest -q tests/commentary_signals
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/l2_themescore
git diff --check
```

Expected: tests pass, principle guard passes, no whitespace errors.

- [ ] **Step 3: Commit and push engineering changes**

Run:

```bash
git add docs/BACKLOG.md docs/superpowers/plans/2026-06-03-commentary-signals-dryrun.md scripts/commentary_signals tests/commentary_signals state/commentary_signals
git commit -m "feat: add commentary signals dry-run"
git push
```

Expected: engineering repo clean and `main...origin/main`.
