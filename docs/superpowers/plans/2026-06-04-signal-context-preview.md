# Signal Context Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ③-D signal_context preview that aggregates accepted commentary and market signals into policy/theme/region context for later ③-E/④ consumption.

**Architecture:** Add `scripts/signal_context` with a preview CLI. It reads only published accepted signals from vault `1_extracted/commentary_signals.jsonl` and `1_extracted/market_intel_signals.jsonl`, reads blocked signals only as an audit gate, writes context JSONL files plus a Chinese HTML report under `state/signal_context/preview_20260604/`.

**Tech Stack:** Python standard library, pytest, existing `python3 -m scripts.<tool>.run` CLI pattern.

---

## Files

- Create: `scripts/signal_context/__init__.py`
- Create: `scripts/signal_context/run.py`
- Create: `scripts/signal_context/report.py`
- Create: `tests/signal_context/__init__.py`
- Create: `tests/signal_context/test_run.py`
- Create live state under: `state/signal_context/preview_20260604/`
- Modify: `docs/BACKLOG.md`

## Task 1: Add Failing Tests

**Files:**
- Create: `tests/signal_context/__init__.py`
- Create: `tests/signal_context/test_run.py`

- [ ] **Step 1: Test policy context aggregation**

Create a temp vault with accepted commentary and market signals. Assert one policy context row has commentary count, market count, commentary role counts, market signal type counts, `attention_level`, `validation_level`, `certainty_adjustment`, and audit refs.

- [ ] **Step 2: Test theme and region context aggregation**

Use commentary-only, market-only, and mixed themes. Assert theme `coverage_warning` values and region rows are driven by market signals only.

- [ ] **Step 3: Test blocked gate and unknown-region exclusion**

Create a blocked signals JSONL containing one commentary id that also appears in accepted signals. Assert preview raises `ValueError`. Create a market signal with empty region code/name and assert it is excluded from region context and counted in summary as `unknown_region_market_signals`.

- [ ] **Step 4: Test output files and report language**

Assert preview writes:

- `policy_context.jsonl`
- `theme_context.jsonl`
- `region_context.jsonl`
- `summary.json`
- `reports/signal_context_preview.html`

Assert the HTML includes Chinese boundary wording: `不写资料库`, `不读取 blocked signals 当 accepted`, and does not include `注入`.

- [ ] **Step 5: Run red tests**

Run:

```bash
python3 -m pytest -q tests/signal_context
```

Expected: fail because `scripts.signal_context` does not exist yet.

## Task 2: Implement Preview CLI

**Files:**
- Create: `scripts/signal_context/__init__.py`
- Create: `scripts/signal_context/run.py`
- Create: `scripts/signal_context/report.py`

- [ ] **Step 1: Implement JSONL IO and signal id helpers**

Read:

- `<vault>/1_extracted/commentary_signals.jsonl`
- `<vault>/1_extracted/market_intel_signals.jsonl`
- optional blocked signal file, default `state/derived_signals/preview_20260604/blocked_signals.jsonl`

Blocked ids are `commentary_id` for commentary and `market_signal_id` for market.

- [ ] **Step 2: Implement accepted-vs-blocked gate**

If any accepted commentary/market signal id appears in blocked ids, raise `ValueError` and write nothing.

- [ ] **Step 3: Implement policy context**

Group commentary by `related_policy_ids`. Group market by `current_policy_id` plus `related_policy_ids` when present. Compute:

- `commentary_signal_count`
- `market_signal_count`
- `commentary_roles`
- `market_signal_types`
- `attention_level`: high if risk count >= 2 or commentary count >= 5; medium if commentary count > 0; else low
- `validation_level`: strong if market count >= 3; medium if >= 2; weak if >= 1; else none
- `certainty_adjustment`: lower if risk or execution exists and market count == 0; raise if market count >= 2 and no risk/execution; else neutral
- `internal_notes`
- `audit_refs`

- [ ] **Step 4: Implement theme context**

Group both signal types by `theme_ids`. Compute counts, dominant roles/types, heat, validation, and `coverage_warning`:

- `commentary_only` if commentary > 0 and market == 0
- `market_only` if market > 0 and commentary == 0
- `thin_evidence` if total signals == 1
- `none` otherwise

- [ ] **Step 5: Implement region context**

Group market signals by non-empty `region.code` and `region.name`. Exclude unknown region rows and count them in summary. Region validation uses market count only.

- [ ] **Step 6: Implement summary and Chinese HTML**

Summary includes input counts, blocked count, context counts, unknown region count, top warnings, and notes: preview only, no vault write, no raw write, no model call, blocked signals audit only.

- [ ] **Step 7: Run green tests**

Run:

```bash
python3 -m pytest -q tests/signal_context
```

Expected: pass.

## Task 3: Run Live Preview

**Files:**
- Create: `state/signal_context/preview_20260604/policy_context.jsonl`
- Create: `state/signal_context/preview_20260604/theme_context.jsonl`
- Create: `state/signal_context/preview_20260604/region_context.jsonl`
- Create: `state/signal_context/preview_20260604/summary.json`
- Create: `state/signal_context/preview_20260604/reports/signal_context_preview.html`

- [ ] **Step 1: Run preview**

Run:

```bash
python3 -m scripts.signal_context.run preview \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state state/signal_context/preview_20260604 \
  --blocked-signals state/derived_signals/preview_20260604/blocked_signals.jsonl
```

Expected: preview state files and Chinese HTML are created. Report must state it does not write vault/raw, does not call a model, and does not treat blocked signals as accepted.

- [ ] **Step 2: Update backlog**

Modify `docs/BACKLOG.md` B12 or B10 with ③-D preview progress and counts.

## Task 4: Verify and Commit

**Files:**
- Commit all created and modified engineering files.

- [ ] **Step 1: Verify**

Run:

```bash
python3 -m pytest -q tests/signal_context
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/signal_context scripts/l2_themescore
git diff --check
git -C "/Users/shaoziyuan/Documents/Zayn Main/政策分析" status --short --branch
```

Expected:

- tests pass
- principle guard passes
- vault remains unchanged except the known pre-existing untracked raw file

- [ ] **Step 2: Commit and push**

Run:

```bash
git add docs/BACKLOG.md docs/superpowers/plans/2026-06-04-signal-context-preview.md \
  scripts/signal_context tests/signal_context
git add -f state/signal_context/preview_20260604
git commit -m "feat: add signal context preview"
git push
```

Expected: engineering repo is clean and pushed.
