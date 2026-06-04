from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .report import render_preview_html


DEFAULT_BLOCKED_SIGNALS = Path("state/derived_signals/preview_20260604/blocked_signals.jsonl")


def _load_jsonl(path: Path, *, required: bool = True) -> list[dict]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ids(rows: list[dict], key: str) -> set[str]:
    return {str(row.get(key) or "") for row in rows if row.get(key)}


def _load_blocked_ids(path: Path | None) -> tuple[set[str], set[str], int]:
    if path is None:
        return set(), set(), 0
    blocked = _load_jsonl(path, required=False)
    return _ids(blocked, "commentary_id"), _ids(blocked, "market_signal_id"), len(blocked)


def _assert_no_blocked_overlap(commentary_rows: list[dict], market_rows: list[dict], blocked_path: Path | None) -> int:
    blocked_commentary, blocked_market, blocked_count = _load_blocked_ids(blocked_path)
    accepted_commentary = _ids(commentary_rows, "commentary_id")
    accepted_market = _ids(market_rows, "market_signal_id")
    overlap = sorted((accepted_commentary & blocked_commentary) | (accepted_market & blocked_market))
    if overlap:
        raise ValueError(f"accepted context includes blocked signal ids: {', '.join(overlap)}")
    return blocked_count


def _level_from_count(count: int, *, weak: str = "weak") -> str:
    if count >= 3:
        return "strong"
    if count >= 2:
        return "medium"
    if count >= 1:
        return weak
    return "none"


def _attention_level(commentary_count: int, roles: Counter) -> str:
    if roles.get("risk", 0) >= 2 or commentary_count >= 5:
        return "high"
    if commentary_count > 0:
        return "medium"
    return "low"


def _certainty_adjustment(roles: Counter, market_count: int) -> str:
    if (roles.get("risk", 0) or roles.get("execution", 0)) and market_count == 0:
        return "lower"
    if market_count >= 2 and not roles.get("risk", 0) and not roles.get("execution", 0):
        return "raise"
    return "neutral"


def _policy_ids_for_market(row: dict) -> list[str]:
    ids = []
    current = str(row.get("current_policy_id") or "")
    if current:
        ids.append(current)
    for pid in row.get("related_policy_ids") or []:
        if pid and pid not in ids:
            ids.append(str(pid))
    return ids


def _internal_notes(roles: Counter, commentary_count: int, market_count: int) -> list[str]:
    notes = []
    if roles.get("risk", 0):
        notes.append("commentary_risk_present")
    if roles.get("execution", 0):
        notes.append("commentary_execution_friction_present")
    if commentary_count and not market_count:
        notes.append("attention_without_market_validation")
    if market_count and not commentary_count:
        notes.append("market_validation_without_commentary_attention")
    if market_count == 1:
        notes.append("market_validation_weak")
    return notes


def build_policy_context(commentary_rows: list[dict], market_rows: list[dict]) -> list[dict]:
    commentary_by_policy: dict[str, list[dict]] = defaultdict(list)
    market_by_policy: dict[str, list[dict]] = defaultdict(list)
    for row in commentary_rows:
        for policy_id in row.get("related_policy_ids") or []:
            if policy_id:
                commentary_by_policy[str(policy_id)].append(row)
    for row in market_rows:
        for policy_id in _policy_ids_for_market(row):
            market_by_policy[policy_id].append(row)

    rows = []
    for policy_id in sorted(set(commentary_by_policy) | set(market_by_policy)):
        comments = commentary_by_policy.get(policy_id, [])
        markets = market_by_policy.get(policy_id, [])
        roles = Counter(str(row.get("signal_role") or "unknown") for row in comments)
        market_types = Counter(str(row.get("signal_type") or "unknown") for row in markets)
        rows.append(
            {
                "policy_id": policy_id,
                "commentary_signal_count": len(comments),
                "market_signal_count": len(markets),
                "commentary_roles": dict(sorted(roles.items())),
                "market_signal_types": dict(sorted(market_types.items())),
                "attention_level": _attention_level(len(comments), roles),
                "validation_level": _level_from_count(len(markets)),
                "certainty_adjustment": _certainty_adjustment(roles, len(markets)),
                "internal_notes": _internal_notes(roles, len(comments), len(markets)),
                "audit_refs": {
                    "commentary_ids": sorted(row["commentary_id"] for row in comments if row.get("commentary_id")),
                    "market_signal_ids": sorted(row["market_signal_id"] for row in markets if row.get("market_signal_id")),
                },
            }
        )
    return rows


def _dominant(counter: Counter, limit: int = 3) -> list[str]:
    return [key for key, _ in counter.most_common(limit)]


def _heat_level(total: int) -> str:
    if total >= 8:
        return "high"
    if total >= 2:
        return "medium"
    if total >= 1:
        return "low"
    return "none"


def _coverage_warning(commentary_count: int, market_count: int) -> str:
    if commentary_count > 0 and market_count == 0:
        return "commentary_only"
    if market_count > 0 and commentary_count == 0:
        return "market_only"
    if commentary_count + market_count == 1:
        return "thin_evidence"
    return "none"


def build_theme_context(commentary_rows: list[dict], market_rows: list[dict]) -> list[dict]:
    commentary_by_theme: dict[str, list[dict]] = defaultdict(list)
    market_by_theme: dict[str, list[dict]] = defaultdict(list)
    for row in commentary_rows:
        for theme_id in row.get("theme_ids") or []:
            if theme_id:
                commentary_by_theme[str(theme_id)].append(row)
    for row in market_rows:
        for theme_id in row.get("theme_ids") or []:
            if theme_id:
                market_by_theme[str(theme_id)].append(row)

    rows = []
    for theme_id in sorted(set(commentary_by_theme) | set(market_by_theme)):
        comments = commentary_by_theme.get(theme_id, [])
        markets = market_by_theme.get(theme_id, [])
        roles = Counter(str(row.get("signal_role") or "unknown") for row in comments)
        market_types = Counter(str(row.get("signal_type") or "unknown") for row in markets)
        rows.append(
            {
                "theme_id": theme_id,
                "commentary_signal_count": len(comments),
                "market_signal_count": len(markets),
                "dominant_commentary_roles": _dominant(roles),
                "dominant_market_signal_types": _dominant(market_types),
                "heat_level": _heat_level(len(comments) + len(markets)),
                "validation_level": _level_from_count(len(markets)),
                "coverage_warning": _coverage_warning(len(comments), len(markets)),
                "audit_refs": {
                    "commentary_ids": sorted(row["commentary_id"] for row in comments if row.get("commentary_id")),
                    "market_signal_ids": sorted(row["market_signal_id"] for row in markets if row.get("market_signal_id")),
                },
            }
        )
    return rows


def build_region_context(market_rows: list[dict]) -> tuple[list[dict], int]:
    by_region: dict[tuple[str, str], list[dict]] = defaultdict(list)
    unknown = 0
    for row in market_rows:
        region = row.get("region") or {}
        code = str(region.get("code") or "")
        name = str(region.get("name") or "")
        if not code or not name:
            unknown += 1
            continue
        by_region[(code, name)].append(row)

    rows = []
    for (code, name), markets in sorted(by_region.items(), key=lambda item: item[0]):
        signal_types = Counter(str(row.get("signal_type") or "unknown") for row in markets)
        theme_ids = sorted({str(theme) for row in markets for theme in (row.get("theme_ids") or []) if theme})
        business_lines = sorted({str(line) for row in markets for line in (row.get("business_lines") or []) if line})
        region_warnings = []
        direct_admin_codes = {"110000", "120000", "310000", "500000"}
        if code.endswith("0000") and code not in {"000000"} | direct_admin_codes and name.endswith("市"):
            region_warnings.append("province_code_with_city_name")
        rows.append(
            {
                "region_code": code,
                "region_name": name,
                "market_signal_count": len(markets),
                "theme_ids": theme_ids,
                "business_lines": business_lines,
                "signal_types": dict(sorted(signal_types.items())),
                "recency_level": "current",
                "validation_level": _level_from_count(len(markets)),
                "region_warnings": region_warnings,
                "audit_refs": {
                    "market_signal_ids": sorted(row["market_signal_id"] for row in markets if row.get("market_signal_id")),
                },
            }
        )
    return rows, unknown


def _summary(
    commentary_rows: list[dict],
    market_rows: list[dict],
    blocked_count: int,
    policy_rows: list[dict],
    theme_rows: list[dict],
    region_rows: list[dict],
    unknown_region_market_signals: int,
) -> dict:
    warnings = Counter(row.get("coverage_warning") for row in theme_rows if row.get("coverage_warning"))
    region_warning_count = sum(len(row.get("region_warnings") or []) for row in region_rows)
    return {
        "accepted_commentary_signals": len(commentary_rows),
        "accepted_market_signals": len(market_rows),
        "blocked_signal_count": blocked_count,
        "policy_context_count": len(policy_rows),
        "theme_context_count": len(theme_rows),
        "region_context_count": len(region_rows),
        "unknown_region_market_signals": unknown_region_market_signals,
        "region_warning_count": region_warning_count,
        "coverage_warnings": dict(sorted(warnings.items())),
        "notes": [
            "preview_only_no_vault_write",
            "raw_unchanged",
            "no_model_call",
            "blocked_signals_audit_only_not_accepted",
            "consumer_default_must_not_show_raw_signal_evidence",
        ],
    }


def run_preview(vault: Path, state: Path, blocked_signals_path: Path | None = DEFAULT_BLOCKED_SIGNALS) -> dict:
    commentary_rows = _load_jsonl(vault / "1_extracted" / "commentary_signals.jsonl")
    market_rows = _load_jsonl(vault / "1_extracted" / "market_intel_signals.jsonl")
    blocked_count = _assert_no_blocked_overlap(commentary_rows, market_rows, blocked_signals_path)

    policy_rows = build_policy_context(commentary_rows, market_rows)
    theme_rows = build_theme_context(commentary_rows, market_rows)
    region_rows, unknown_region_market_signals = build_region_context(market_rows)
    summary = _summary(
        commentary_rows,
        market_rows,
        blocked_count,
        policy_rows,
        theme_rows,
        region_rows,
        unknown_region_market_signals,
    )

    _write_jsonl(state / "policy_context.jsonl", policy_rows)
    _write_jsonl(state / "theme_context.jsonl", theme_rows)
    _write_jsonl(state / "region_context.jsonl", region_rows)
    _write_json(state / "summary.json", summary)
    report_path = render_preview_html(
        summary,
        policy_rows,
        theme_rows,
        region_rows,
        state / "reports" / "signal_context_preview.html",
    )
    return {
        "summary": summary,
        "policy_context_path": str(state / "policy_context.jsonl"),
        "theme_context_path": str(state / "theme_context.jsonl"),
        "region_context_path": str(state / "region_context.jsonl"),
        "summary_path": str(state / "summary.json"),
        "report_path": str(report_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--vault", type=Path, required=True)
    preview.add_argument("--state", type=Path, required=True)
    preview.add_argument("--blocked-signals", type=Path, default=DEFAULT_BLOCKED_SIGNALS)

    args = parser.parse_args(argv)
    if args.mode == "preview":
        result = run_preview(args.vault, args.state, args.blocked_signals)
    else:
        raise SystemExit(f"unsupported mode: {args.mode}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
