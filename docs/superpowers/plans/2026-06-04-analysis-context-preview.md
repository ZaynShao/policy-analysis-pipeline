# Analysis Context Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ③-E preview that merges high-precision policy relation candidates and closed-loop signal_context into one policy-level `analysis_context` for ④.

**Architecture:** Read only existing preview files from `state/analysis_layer/preview_20260604` and `state/signal_context/preview_20260604`. Produce machine JSONL/JSON and a Chinese HTML report under engineering `state/`; do not write vault, raw, or apply outputs.

**Tech Stack:** Python standard library, pytest, existing pipeline module layout.

---

### File Map

- Create: `scripts/analysis_context/__init__.py`
  - Marks the module.
- Create: `scripts/analysis_context/run.py`
  - Loads relation candidates and policy signal context.
  - Aggregates relation in/out counts by policy.
  - Merges signal summaries and audit refs.
  - Writes `analysis_context.jsonl` and `analysis_context_summary.json`.
- Create: `scripts/analysis_context/report.py`
  - Renders Chinese HTML preview.
- Create: `tests/analysis_context/__init__.py`
  - Marks tests as a package.
- Create: `tests/analysis_context/test_run.py`
  - Covers relation/signal merge behavior, relation-only/signal-only rows, schema gates, and HTML boundaries.
- Modify: `docs/BACKLOG.md`
  - Record B10 progress after real preview is generated.

### Task 1: Red Tests

**Files:**
- Create: `tests/analysis_context/__init__.py`
- Create: `tests/analysis_context/test_run.py`

- [ ] **Step 1: Write failing tests**

Write tests that import `run_preview` from `scripts.analysis_context.run` and assert:

```python
def test_analysis_context_merges_relation_and_signal_summaries(tmp_path):
    relations = tmp_path / "relations.jsonl"
    policy_context = tmp_path / "policy_context.jsonl"
    state = tmp_path / "state"
    write_jsonl(relations, [
        relation("HPR_basis", "P_A", "P_B", "cites_basis"),
        relation("HPR_sup", "P_C", "P_A", "supersedes"),
        relation("HPR_clarify", "P_A", "P_D", "clarifies"),
    ])
    write_jsonl(policy_context, [signal_row("P_A")])

    result = run_preview(relations, policy_context, state)

    p_a = row_by_policy(state / "analysis_context.jsonl")["P_A"]
    assert p_a["relation_summary"]["cites_basis_out"] == 1
    assert p_a["relation_summary"]["superseded_by_count"] == 1
    assert p_a["relation_summary"]["clarifies_out"] == 1
    assert p_a["signal_summary"]["commentary_signal_count"] == 2
    assert p_a["signal_summary"]["market_signal_count"] == 1
    assert set(p_a["audit_refs"]["relation_candidate_ids"]) == {"HPR_basis", "HPR_sup", "HPR_clarify"}
    assert {"has_basis_chain", "superseded_by_policy", "has_clarification", "market_validation_weak", "certainty_lower"} <= set(p_a["analysis_flags"])
    assert result["summary"]["rows_with_both"] == 1
```

- [ ] **Step 2: Verify red**

Run:

```bash
python3 -m pytest -q tests/analysis_context
```

Expected: import failure because `scripts.analysis_context` does not exist.

### Task 2: Minimal Implementation

**Files:**
- Create: `scripts/analysis_context/__init__.py`
- Create: `scripts/analysis_context/run.py`
- Create: `scripts/analysis_context/report.py`

- [ ] **Step 1: Implement `run_preview`**

Implementation contract:

```python
def run_preview(relations_path: Path, policy_context_path: Path, state: Path) -> dict:
    ...
```

Required outputs:

- `state / "analysis_context.jsonl"`
- `state / "analysis_context_summary.json"`
- `state / "reports" / "analysis_context_preview.html"`

Required row shape:

```json
{
  "policy_id": "P_xxx",
  "relation_summary": {
    "references_out": 0,
    "references_in": 0,
    "cites_basis_out": 0,
    "cites_basis_in": 0,
    "supersedes_out": 0,
    "superseded_by_count": 0,
    "clarifies_out": 0,
    "clarified_by_count": 0
  },
  "signal_summary": {
    "commentary_signal_count": 0,
    "market_signal_count": 0,
    "commentary_attention": "low",
    "market_validation": "none",
    "certainty_adjustment": "neutral",
    "internal_notes": []
  },
  "analysis_flags": [],
  "audit_refs": {
    "relation_candidate_ids": [],
    "commentary_ids": [],
    "market_signal_ids": []
  }
}
```

- [ ] **Step 2: Verify green**

Run:

```bash
python3 -m pytest -q tests/analysis_context
```

Expected: all tests pass.

### Task 3: Real Preview

**Files:**
- Generated: `state/analysis_layer/preview_20260604/analysis_context.jsonl`
- Generated: `state/analysis_layer/preview_20260604/analysis_context_summary.json`
- Generated: `state/analysis_layer/preview_20260604/reports/analysis_context_preview.html`

- [ ] **Step 1: Run preview**

```bash
python3 -m scripts.analysis_context.run preview \
  --relations state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl \
  --policy-context state/signal_context/preview_20260604/policy_context.jsonl \
  --state state/analysis_layer/preview_20260604
```

- [ ] **Step 2: Inspect summary**

Confirm counts for relation candidates, policy_context rows, rows with both, rows relation-only, rows signal-only, and rows by flag.

### Task 4: Docs And Verification

**Files:**
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Record B10 progress**

Append a short dated note for ③-E preview output paths and summary counts.

- [ ] **Step 2: Verify principles**

Run:

```bash
python3 -m pytest -q tests/analysis_context
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/analysis_context scripts/l2_themescore
git diff --check
git -C "/Users/shaoziyuan/Documents/Zayn Main/政策分析" -c core.quotePath=false status --short --branch
rg -n "注入|injected|stance|直接生成|机械" scripts/analysis_context tests/analysis_context docs/BACKLOG.md state/analysis_layer/preview_20260604/reports/analysis_context_preview.html || true
```

Expected:

- Tests pass.
- Principle guard has no PID literals in source.
- Vault status has only the known untracked raw file.
- HTML says preview-only and no model call.

### Task 5: Commit

- [ ] **Step 1: Add explicit files**

```bash
git add docs/superpowers/plans/2026-06-04-analysis-context-preview.md \
  scripts/analysis_context \
  tests/analysis_context \
  docs/BACKLOG.md
git add -f state/analysis_layer/preview_20260604/analysis_context.jsonl \
  state/analysis_layer/preview_20260604/analysis_context_summary.json \
  state/analysis_layer/preview_20260604/reports/analysis_context_preview.html
```

- [ ] **Step 2: Commit and push**

```bash
git commit -m "feat: add analysis context preview"
git push
```
