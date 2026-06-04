# Derived Signals Preview/Apply Contract Design

## Context

`commentary_signals` and `market_intel_signals` already produce reproducible dry-run state:

- `state/commentary_signals/dryrun_20260603/signals.jsonl`
- `state/commentary_signals/dryrun_20260603/review_queue.jsonl`
- `state/market_intel_signals/dryrun_20260603/market_signals.jsonl`
- `state/market_intel_signals/dryrun_20260603/review_queue.jsonl`

The next step is not another classifier and not a manual PID fix. The next step is a publish contract that turns accepted dry-run signal rows into vault-shaped derived files, with an explicit preview/apply boundary.

## Goal

Create `scripts/derived_signals` so the pipeline can preview and later apply two derived files:

- `1_extracted/commentary_signals.jsonl`
- `1_extracted/market_intel_signals.jsonl`

## Boundaries

1. Preview consumes only accepted signal files:
   - commentary: `signals.jsonl`
   - market intel: `market_signals.jsonl`
2. Preview must read review queues as a publish gate.
3. Preview must exclude any signal row whose stable key overlaps review queue.
   - commentary: `commentary_id`
   - market intel: `source_pid` / `current_policy_id` / `raw_path`
4. Apply consumes preview output files only, not the original upstream dry-run directories.
5. Apply may write only whole files under `1_extracted/`.
6. Apply must never touch `0_raw/`.
7. Live vault apply requires explicit user approval. This task runs live preview only.

## Data Semantics

These signals are internal policy-intelligence parameters:

- Commentary signals calibrate and audit how outside readings interpret policy risk, opportunity, execution friction, and attention.
- Market-intel signals validate whether project, capacity, subsidy, price, tender, access, or landing activity exists in the real market.

They are not consumer-facing proof that a conclusion was mechanically produced from outside views or market signals. Consumer-facing outputs should expose policy basis and business conclusion by default; commentary and market signals are surfaced only for traceability, audit, or analyst review.

## Preview Outputs

`python3 -m scripts.derived_signals.run preview ...` writes:

- `commentary_signals.jsonl`
- `market_intel_signals.jsonl`
- `blocked_signals.jsonl`
- `summary.json`
- `reports/derived_signals_preview.html`

Preview summary records:

- accepted commentary signal count
- accepted market-intel signal count
- commentary review-queue count
- market-intel review-queue count
- blocked signal count
- planned vault target paths
- source dry-run directories

## Apply Outputs

`python3 -m scripts.derived_signals.run apply ...` writes:

- `<vault>/1_extracted/commentary_signals.jsonl`
- `<vault>/1_extracted/market_intel_signals.jsonl`

It also writes engineering evidence beside the preview:

- `apply_summary.json`
- `apply_log.jsonl`
- `reports/derived_signals_apply.html`

## Review Pool Closure

Review queues remain unresolved after preview. They are not failures and not accepted data. Any overlapping signal is blocked from publish and recorded in preview evidence. Their closure path is:

1. Global rules cannot decide.
2. Row enters upstream review queue.
3. Human reads evidence and gives a data-level decision.
4. The decision returns through the normal upstream dry-run/apply flow.
5. Repeating patterns become registry, prompt, classifier, or program-gate changes.

This keeps the mechanism reproducible: another similar file should enter the same review path instead of being handled by source-code special cases.
