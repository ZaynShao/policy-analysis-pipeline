# Derived Signals Preview/Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible preview/apply contract for commentary and market-intel derived signals.

**Architecture:** `scripts/derived_signals` reads existing upstream dry-run signal files, writes preview files and a Chinese HTML report, then can apply those preview files into `1_extracted/` only. The live task stops after preview; apply is implemented and tested against temporary vaults so a later approved live apply is deterministic.

**Tech Stack:** Python standard library, pytest, existing repository CLI pattern using `python3 -m scripts.<tool>.run`.

---

## Files

- Create: `scripts/derived_signals/__init__.py`
- Create: `scripts/derived_signals/run.py`
- Create: `scripts/derived_signals/report.py`
- Create: `tests/derived_signals/__init__.py`
- Create: `tests/derived_signals/test_run.py`
- Modify: `SCHEMA.md`
- Modify: `docs/BACKLOG.md`

## Task 1: Add Failing Contract Tests

**Files:**
- Create: `tests/derived_signals/__init__.py`
- Create: `tests/derived_signals/test_run.py`

- [ ] **Step 1: Write tests**

Write tests for:

1. Preview writes two derived JSONL files, summary, and HTML report.
2. Preview uses review-queue rows as a publish gate and excludes overlapping signal rows.
3. Apply writes only `1_extracted/commentary_signals.jsonl` and `1_extracted/market_intel_signals.jsonl` from preview output.
4. Apply refuses missing preview files.

- [ ] **Step 2: Run red test**

Run:

```bash
python3 -m pytest -q tests/derived_signals
```

Expected: fail because `scripts.derived_signals` does not exist yet.

## Task 2: Implement Preview/Apply

**Files:**
- Create: `scripts/derived_signals/__init__.py`
- Create: `scripts/derived_signals/run.py`
- Create: `scripts/derived_signals/report.py`

- [ ] **Step 1: Implement preview helpers**

Implement:

- `build_preview(commentary_state, market_state, state)`
- JSONL load/write helpers
- per-row normalization with `schema_version`, `source_kind`, `sanitized_from`, and `extracted_by`
- queue overlap blocking with `blocked_signals.jsonl`

- [ ] **Step 2: Implement apply helper**

Implement:

- `apply_preview(vault, preview_state)`
- target-path guard requiring `1_extracted/`
- whole-file writes from preview output files only
- apply summary/log/report in the preview state

- [ ] **Step 3: Implement CLI**

Implement:

```bash
python3 -m scripts.derived_signals.run preview --commentary-state ... --market-state ... --state ...
python3 -m scripts.derived_signals.run apply --vault ... --preview-state ...
```

- [ ] **Step 4: Run green tests**

Run:

```bash
python3 -m pytest -q tests/derived_signals
```

Expected: pass.

## Task 3: Document Schema and Backlog

**Files:**
- Modify: `SCHEMA.md`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Document L2 files**

Add `1_extracted/commentary_signals.jsonl` and `1_extracted/market_intel_signals.jsonl` to the schema tree and L2 section. The language must say these are internal calibration/validation signals, not consumer-facing proof text.

- [ ] **Step 2: Update B12 progress**

Record that preview/apply contract now exists and live preview has been produced, while live vault apply remains unrun until explicit approval.

## Task 4: Run Live Preview and Verify

**Files:**
- Create: `state/derived_signals/preview_20260604/commentary_signals.jsonl`
- Create: `state/derived_signals/preview_20260604/market_intel_signals.jsonl`
- Create: `state/derived_signals/preview_20260604/summary.json`
- Create: `state/derived_signals/preview_20260604/blocked_signals.jsonl`
- Create: `state/derived_signals/preview_20260604/reports/derived_signals_preview.html`

- [ ] **Step 1: Run preview**

Run:

```bash
python3 -m scripts.derived_signals.run preview \
  --commentary-state state/commentary_signals/dryrun_20260603 \
  --market-state state/market_intel_signals/dryrun_20260603 \
  --state state/derived_signals/preview_20260604
```

Expected: output summary shows 189 commentary signals, 23 market-intel signals, 18 commentary queue rows, and 14 market-intel queue rows.

- [ ] **Step 2: Verify**

Run:

```bash
python3 -m pytest -q tests/derived_signals
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/l2_themescore
git diff --check
```

Expected: all pass.

## Task 5: Commit and Push

**Files:**
- Commit all created and modified files.

- [ ] **Step 1: Inspect status**

Run:

```bash
git status --short --branch
git -C "/Users/shaoziyuan/Documents/Zayn Main/政策分析" status --short --branch
```

Expected: engineering repo has only this task's changes; vault repo remains clean.

- [ ] **Step 2: Commit and push**

Run:

```bash
git add docs/superpowers/specs/2026-06-04-derived-signals-contract-design.md \
  docs/superpowers/plans/2026-06-04-derived-signals-preview-apply.md \
  scripts/derived_signals tests/derived_signals SCHEMA.md docs/BACKLOG.md \
  state/derived_signals/preview_20260604
git commit -m "feat: add derived signals preview contract"
git push
```

Expected: engineering repo clean and `main...origin/main`.
