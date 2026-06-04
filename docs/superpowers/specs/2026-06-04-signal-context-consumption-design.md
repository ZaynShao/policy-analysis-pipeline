# Signal Context Consumption Design

## 1. Position

This design belongs to **政策情报四层重构**:

- ② has now published closed-loop derived signals:
  - `1_extracted/commentary_signals.jsonl`
  - `1_extracted/market_intel_signals.jsonl`
- ② also blocks pending-review signals:
  - `state/derived_signals/preview_20260604/blocked_signals.jsonl`
- ③/④ need a read contract so downstream products use signals without turning internal calibration into default consumer-facing rationale.

Chosen approach: **③ builds internal signal context; ④ reads context, not raw signals by default**.

## 2. Goal

Build a reproducible `signal_context` layer that answers:

- Which policies have commentary attention, risk, opportunity, execution-friction, or interpretation signals?
- Which themes have market validation signals?
- Which regions have observable project, capacity, subsidy, tender, price, access, or landing signals?
- Where should downstream analysis raise attention, lower certainty, or flag insufficient validation?

The layer must improve decision quality without changing raw facts, policy attribution, policy themes, or business scores.

## 3. Non-Goals

This design does not:

- change `0_raw/`
- write `business_view.scores`
- modify policy theme assignment
- consume review queues
- publish pending-review signals
- expose commentary or market-intel evidence as default consumer-facing rationale
- regenerate stale policy relations
- implement ④ report UI

## 4. Inputs

Primary inputs:

- `1_extracted/commentary_signals.jsonl`
- `1_extracted/market_intel_signals.jsonl`

Optional contextual inputs for aggregation only:

- `_meta/business_view/*.yaml`
- `1_extracted/relations/*.jsonl`
- `_meta/themes_registry.yaml`
- policy frontmatter under `0_raw/policies/*.md` as read-only metadata

Forbidden inputs:

- upstream `review_queue.jsonl` as accepted data
- `state/derived_signals/*/blocked_signals.jsonl` as accepted data
- old isolated `business_view` backup
- legacy archive outputs

`blocked_signals.jsonl` may be used only for audit reporting: "these signals are pending and therefore excluded."

## 5. Outputs

First implementation should be preview-only:

- `state/signal_context/preview_YYYYMMDD/policy_context.jsonl`
- `state/signal_context/preview_YYYYMMDD/theme_context.jsonl`
- `state/signal_context/preview_YYYYMMDD/region_context.jsonl`
- `state/signal_context/preview_YYYYMMDD/summary.json`
- `state/signal_context/preview_YYYYMMDD/reports/signal_context_preview.html`

Later apply, if approved, may publish:

- `1_extracted/signal_context/policy_context.jsonl`
- `1_extracted/signal_context/theme_context.jsonl`
- `1_extracted/signal_context/region_context.jsonl`

Apply must consume preview files only and write whole files under `1_extracted/signal_context/`.

## 6. Policy Context

`policy_context.jsonl` groups accepted commentary and market signals by policy id.

Required fields:

```json
{
  "policy_id": "P_xxx",
  "commentary_signal_count": 3,
  "market_signal_count": 1,
  "commentary_roles": {"risk": 1, "opportunity": 2},
  "market_signal_types": {"project_list": 1},
  "attention_level": "low|medium|high",
  "validation_level": "none|weak|medium|strong",
  "certainty_adjustment": "lower|neutral|raise",
  "internal_notes": ["commentary_risk_present", "market_validation_weak"],
  "audit_refs": {
    "commentary_ids": ["C_xxx"],
    "market_signal_ids": ["MI_xxx"]
  }
}
```

Rules:

- Commentary can raise attention or lower certainty.
- Market intel can raise validation if signal type is concrete and dated.
- Neither can rewrite policy facts or scores.
- If evidence conflicts with policy-only judgment, output an internal note, not a score mutation.

## 7. Theme Context

`theme_context.jsonl` groups accepted signals by theme id.

Required fields:

```json
{
  "theme_id": "energy_storage_theme",
  "commentary_signal_count": 12,
  "market_signal_count": 4,
  "dominant_commentary_roles": ["opportunity", "execution"],
  "dominant_market_signal_types": ["project_list", "capacity_disclosure"],
  "heat_level": "low|medium|high",
  "validation_level": "none|weak|medium|strong",
  "coverage_warning": "none|commentary_only|market_only|thin_evidence",
  "audit_refs": {
    "commentary_ids": ["C_xxx"],
    "market_signal_ids": ["MI_xxx"]
  }
}
```

Rules:

- A theme with many commentary signals but no market signal is "attention without validation."
- A theme with market signals but weak policy/business context is "market signal requires policy check."
- `coverage_warning` is for internal routing and analyst review, not default public text.

## 8. Region Context

`region_context.jsonl` groups accepted market signals by administrative region.

Required fields:

```json
{
  "region_code": "640100",
  "region_name": "银川市",
  "market_signal_count": 2,
  "theme_ids": ["energy_storage_theme"],
  "business_lines": ["power"],
  "signal_types": {"project_list": 1, "capacity_disclosure": 1},
  "recency_level": "unknown|old|current",
  "validation_level": "weak|medium|strong",
  "audit_refs": {
    "market_signal_ids": ["MI_xxx"]
  }
}
```

Rules:

- Region context is driven by market signals first.
- Commentary can be linked through policy/theme, but should not create region validation by itself.
- Unknown-region market signals should already be blocked upstream and must not appear here.

## 9. ④ Consumption Contract

Default consumer-facing outputs may use signal context only to shape:

- attention level
- certainty language
- validation warnings
- analyst follow-up flags

Default consumer-facing outputs may show:

- policy basis
- business judgment
- impact and suggested actions
- explicit uncertainty such as "落地信号不足" or "市场验证较弱"

Default consumer-facing outputs must not show:

- raw commentary titles
- raw market-intel titles
- signal evidence snippets
- source-account lists
- wording that implies conclusions are directly generated from commentary or market signals

Audit mode may show:

- signal counts
- signal ids
- source titles
- evidence snippets
- confidence values
- links back to `sanitized_from`

Audit mode must be explicit. It cannot be the default card/report mode.

## 10. Review Queue Contract

Review queue remains a gate:

1. Upstream creates a signal candidate.
2. If the signal overlaps review queue, `derived_signals` blocks it.
3. Blocked signals remain audit evidence only.
4. Human review gives a data-level decision.
5. The decision returns through upstream dry-run/preview/apply.
6. Only then may the signal enter `1_extracted/*signals.jsonl`.

`signal_context` must never read blocked signals as accepted inputs.

## 11. Preview Gates

The preview report must include:

- input file paths and row counts
- accepted commentary signal count
- accepted market signal count
- blocked signal count from the latest derived preview
- policy/theme/region context counts
- top internal warnings
- proof that no review-queue overlap entered context

The preview must fail if:

- an accepted context row references a blocked signal id
- an accepted context row references a missing signal id
- region context includes unknown region
- output path is outside `state/signal_context/`

## 12. Apply Gates

Apply requires explicit user approval.

Apply must:

- read preview outputs only
- write only `1_extracted/signal_context/*.jsonl`
- write whole files
- produce `apply_summary.json`, `apply_log.jsonl`, and an HTML apply report
- keep `0_raw/` unchanged

Apply must fail if:

- preview files are missing
- preview summary reports any gate failure
- output targets are outside `1_extracted/signal_context/`

## 13. Testing Strategy

Required tests:

- Policy context aggregates commentary roles and market signal types without mutating scores.
- Theme context marks commentary-only and market-only coverage warnings.
- Region context excludes unknown-region signals.
- Blocked signal ids cannot appear in any context output.
- Apply writes only from preview into `1_extracted/signal_context/`.
- Reports contain Chinese human-facing explanations and do not use forbidden wording.

Verification commands:

```bash
python3 -m pytest -q tests/signal_context
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/l2_themescore
git diff --check
```

## 14. Scope Boundary

This is one implementation unit:

- Build `signal_context` preview/apply around already-published derived signals.
- Do not rebuild ③ policy relations yet.
- Do not build final ④ report UI yet.

After this unit is working, ③ relation regeneration and ④ report/card design can read `signal_context` as a stable internal input.
