# Market Intel Signals Dry-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert existing `market_intel_manifest.jsonl` rows into deterministic internal market validation signals.

**Architecture:** Read the manifest, locate current raw policy files by `id` or alias, classify signal type/theme/business line from title/body using registry aliases and keyword rules, then write engineering state and a Chinese HTML report. The dry-run never writes the vault and never calls an LLM.

**Tech Stack:** Python 3, PyYAML, pytest, existing theme registry and pipeline state.

---

### Task 1: Extractor Tests

**Files:**
- Create: `tests/market_intel_signals/__init__.py`
- Create: `tests/market_intel_signals/test_extractor.py`
- Create: `scripts/market_intel_signals/__init__.py`
- Create: `scripts/market_intel_signals/extractor.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from scripts.market_intel_signals.extractor import (
    classify_signal_type,
    extract_market_signal,
    locate_policy_by_id_or_alias,
    parse_policy_file,
)


def test_locate_policy_by_alias(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    path = root / "policy.md"
    path.write_text("---\nid: P_NEW\naliases: [P_OLD]\ntitle: old alias\n---\n正文", encoding="utf-8")

    found = locate_policy_by_id_or_alias(root, "P_OLD")

    assert found == path


def test_classify_signal_type_project_list():
    assert classify_signal_type("银川电网侧储能项目清单公示", "") == "project_list"


def test_extract_signal_uses_theme_region_and_business_lines(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    path = root / "policy.md"
    path.write_text(
        "---\nid: P_NEW\naliases: [P_OLD]\ntitle: 南方电网首个交流V2G落地海口\n"
        "date: '2025-12-27'\nregion: {level: 市, code: '460100', name: 海口市}\n"
        "provenance: {url: 'https://example.com'}\n---\n车网互动项目正式投运。",
        encoding="utf-8",
    )
    doc = parse_policy_file(path, root)

    signal = extract_market_signal({"pid": "P_OLD"}, doc, {"v2g": ["V2G", "车网互动"]})

    assert signal.current_policy_id == "P_NEW"
    assert signal.theme_ids == ["v2g"]
    assert signal.business_lines == ["charging", "power"]
    assert signal.signal_type == "pilot_landing"
    assert signal.time_validity == "point_in_time"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/market_intel_signals/test_extractor.py`

Expected: FAIL because `scripts.market_intel_signals` does not exist.

- [ ] **Step 3: Implement minimal extractor**

Implement:
- frontmatter parser
- lookup by current `id` or `aliases`
- stable `MI_` ID from source PID and raw path
- keyword signal-type classifier
- theme matching via registry aliases
- business-line mapping from theme IDs
- short sanitized evidence

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/market_intel_signals/test_extractor.py`

Expected: PASS.

### Task 2: Runner And Report Tests

**Files:**
- Create: `tests/market_intel_signals/test_run.py`
- Create: `scripts/market_intel_signals/report.py`
- Create: `scripts/market_intel_signals/run.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from pathlib import Path

from scripts.market_intel_signals.run import run_dryrun


def test_dryrun_writes_state_and_html_without_modifying_vault(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    policies = vault / "0_raw" / "policies"
    meta = vault / "_meta"
    policies.mkdir(parents=True)
    meta.mkdir(parents=True)
    (meta / "themes_registry.yaml").write_text(
        "themes:\n  - id: v2g\n    zh: V2G\n    aliases: [V2G, 车网互动]\n",
        encoding="utf-8",
    )
    raw = policies / "p.md"
    raw.write_text(
        "---\nid: P_NEW\naliases: [P_OLD]\ntitle: 南方电网首个交流V2G落地海口\n"
        "date: '2025-12-27'\nregion: {level: 市, code: '460100', name: 海口市}\n---\n车网互动项目正式投运。",
        encoding="utf-8",
    )
    manifest = state / "source_ready" / "market_intel_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"pid": "P_OLD", "class": "market_intel"}, ensure_ascii=False) + "\n", encoding="utf-8")
    before = raw.read_text(encoding="utf-8")

    result = run_dryrun(vault, manifest, state / "market")

    assert result["summary"]["emitted_signals"] == 1
    assert raw.read_text(encoding="utf-8") == before
    assert (state / "market" / "market_signals.jsonl").exists()
    assert (state / "market" / "review_queue.jsonl").exists()
    assert (state / "market" / "summary.json").exists()
    assert (state / "market" / "reports" / "market_intel_signals_dryrun.html").exists()


def test_dryrun_queues_missing_pid(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    (vault / "0_raw" / "policies").mkdir(parents=True)
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "themes_registry.yaml").write_text("themes: []\n", encoding="utf-8")
    manifest = state / "source_ready" / "market_intel_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"pid": "P_MISSING", "class": "market_intel"}, ensure_ascii=False) + "\n", encoding="utf-8")

    result = run_dryrun(vault, manifest, state / "market")

    assert result["summary"]["emitted_signals"] == 0
    assert result["summary"]["review_queue"] == 1
    row = json.loads((state / "market" / "review_queue.jsonl").read_text(encoding="utf-8").strip())
    assert row["reason"] == "manifest_pid_not_found"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/market_intel_signals/test_run.py`

Expected: FAIL because `run_dryrun` does not exist.

- [ ] **Step 3: Implement runner and report**

Implement:
- `run_dryrun(vault, manifest, state)` writes `market_signals.jsonl`, `review_queue.jsonl`, `summary.json`, HTML
- queue reasons: missing PID, no theme, unknown region, missing date, unknown type
- report states market signals are internal validation parameters

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/market_intel_signals`

Expected: PASS.

### Task 3: Live Dry-Run And Verification

**Files:**
- Create: `state/market_intel_signals/dryrun_20260603/market_signals.jsonl`
- Create: `state/market_intel_signals/dryrun_20260603/review_queue.jsonl`
- Create: `state/market_intel_signals/dryrun_20260603/summary.json`
- Create: `state/market_intel_signals/dryrun_20260603/reports/market_intel_signals_dryrun.html`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Run live dry-run**

Run:

```bash
python3 -m scripts.market_intel_signals.run dry-run \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --manifest state/source_ready/market_intel_manifest.jsonl \
  --state state/market_intel_signals/dryrun_20260603
```

Expected: writes engineering state only; vault status remains clean.

- [ ] **Step 2: Verify**

Run:

```bash
python3 -m pytest -q tests/market_intel_signals
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/l2_themescore
git diff --check
```

Expected: pass.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add docs/BACKLOG.md docs/superpowers/specs/2026-06-03-market-intel-signals-design.md docs/superpowers/plans/2026-06-03-market-intel-signals-dryrun.md scripts/market_intel_signals tests/market_intel_signals
git add -f state/market_intel_signals/dryrun_20260603
git commit -m "feat: add market intel signals dry-run"
git push
```

Expected: engineering repo clean and `main...origin/main`.
