# Market Intel Signals Design

## Goal

Build a minimal, deterministic representation for `market_intel` so the third source can participate in later analysis as an internal validation signal.

This is a dry-run design only. It does not create a new vault directory, does not move raw files, does not edit `0_raw`, and does not call an LLM.

## Source Boundary

Input is the existing manifest:

```text
state/source_ready/market_intel_manifest.jsonl
```

Each row is a previously reviewed item marked as `class: market_intel` and `kept_in: 0_raw/policies`. The dry-run locates the current raw file by matching either:

- current frontmatter `id`, or
- current frontmatter `aliases` containing the manifest PID.

The current raw `id` may differ from the manifest PID because ②-A identity repair can preserve old IDs in aliases. The dry-run records both values.

## Output Fields

Each emitted signal has only fields with a direct consumer:

```yaml
market_signal_id: MI_xxx
source_pid: P_xxx
current_policy_id: P_xxx
raw_path: 0_raw/policies/...
title: source title
region:
  level: 市
  code: "330100"
  name: 杭州市
theme_ids: [v2g, charging_infra]
business_lines: [charging, power]
signal_type: project_list|competitive_allocation|project_commissioned|pilot_landing|capacity_disclosure|subsidy_list|price_signal|trading_result|tender_procurement|market_access|project_progress|project_case|unknown
observed_date: "2026-03-27"
time_validity: quarterly|price_window|point_in_time|unknown
related_policy_ids: []
confidence: 0.0-1.0
evidence: short excerpt
source_url: URL
```

`related_policy_ids` remains empty unless a deterministic current-source rule identifies it. The first dry-run does not consume stale old relation files as truth.

## Review Queue

A row can still emit a signal and enter review queue. Queue reasons are:

- `manifest_pid_not_found`
- `theme_not_found`
- `region_unknown`
- `date_missing`
- `signal_type_unknown`

This is the same principle as the manual pool used elsewhere: global deterministic rules classify what they can; missing or uncertain dimensions go to review; review results must later return through normal dry-run/apply, not source-code PID branches.

## Consumer Boundary

Market signals are internal validation parameters. They can support later answers such as:

- a theme has real projects, capacity, price movement, subsidy lists, or permits;
- a region has observable execution;
- a policy direction has weak/strong market follow-through.

They should not be described to an external reader as a visible market-source proof chain behind the conclusion. Public-facing output can show conclusions, implications, recommendations, and necessary policy basis; market signals are available for audit and traceability.

## Done Gate

The dry-run is done when:

- all manifest rows are represented as either signals or queue rows;
- no raw files are modified;
- output includes `market_signals.jsonl`, `review_queue.jsonl`, `summary.json`, and a Chinese HTML report;
- tests cover ID/alias lookup, signal classification, queue reasons, and no-vault-write behavior;
- full pytest and the existing ②-B principle guard pass.
