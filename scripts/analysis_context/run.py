from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .report import render_preview_html


RELATIONS = ["references", "cites_basis", "supersedes", "clarifies"]


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


def _empty_relation_summary() -> dict:
    return {
        "references_out": 0,
        "references_in": 0,
        "cites_basis_out": 0,
        "cites_basis_in": 0,
        "supersedes_out": 0,
        "superseded_by_count": 0,
        "clarifies_out": 0,
        "clarified_by_count": 0,
        "other_rel_counts": {},
    }


def _empty_signal_summary() -> dict:
    return {
        "commentary_signal_count": 0,
        "market_signal_count": 0,
        "commentary_attention": "low",
        "market_validation": "none",
        "certainty_adjustment": "neutral",
        "internal_notes": [],
    }


def _empty_audit_refs() -> dict:
    return {
        "relation_candidate_ids": [],
        "commentary_ids": [],
        "market_signal_ids": [],
    }


def _require_relation_field(row: dict, field: str) -> str:
    value = str(row.get(field) or "")
    if not value:
        raise ValueError(f"relation row missing required field: {field}")
    return value


def _relation_candidate_id(row: dict) -> str:
    value = str(row.get("candidate_id") or row.get("source") or "")
    if not value:
        raise ValueError("relation row missing required field: candidate_id")
    return value


def _aggregate_relations(rows: list[dict]) -> tuple[dict[str, dict], dict[str, set[str]]]:
    relation_by_policy: dict[str, dict] = {}
    refs_by_policy: dict[str, set[str]] = {}

    def ensure(policy_id: str) -> None:
        relation_by_policy.setdefault(policy_id, _empty_relation_summary())
        refs_by_policy.setdefault(policy_id, set())

    for row in rows:
        candidate_id = _relation_candidate_id(row)
        source = _require_relation_field(row, "from")
        target = _require_relation_field(row, "to")
        rel = _require_relation_field(row, "rel")

        ensure(source)
        ensure(target)
        refs_by_policy[source].add(candidate_id)
        refs_by_policy[target].add(candidate_id)

        if rel == "references":
            relation_by_policy[source]["references_out"] += 1
            relation_by_policy[target]["references_in"] += 1
        elif rel == "cites_basis":
            relation_by_policy[source]["cites_basis_out"] += 1
            relation_by_policy[target]["cites_basis_in"] += 1
        elif rel == "supersedes":
            relation_by_policy[source]["supersedes_out"] += 1
            relation_by_policy[target]["superseded_by_count"] += 1
        elif rel == "clarifies":
            relation_by_policy[source]["clarifies_out"] += 1
            relation_by_policy[target]["clarified_by_count"] += 1
        else:
            relation_by_policy[source]["other_rel_counts"][rel] = (
                relation_by_policy[source]["other_rel_counts"].get(rel, 0) + 1
            )
            relation_by_policy[target]["other_rel_counts"][rel] = (
                relation_by_policy[target]["other_rel_counts"].get(rel, 0) + 1
            )

    return relation_by_policy, refs_by_policy


def _signal_summary(row: dict | None) -> dict:
    if not row:
        return _empty_signal_summary()
    return {
        "commentary_signal_count": int(row.get("commentary_signal_count") or 0),
        "market_signal_count": int(row.get("market_signal_count") or 0),
        "commentary_attention": str(row.get("attention_level") or "low"),
        "market_validation": str(row.get("validation_level") or "none"),
        "certainty_adjustment": str(row.get("certainty_adjustment") or "neutral"),
        "internal_notes": list(row.get("internal_notes") or []),
    }


def _signal_audit_refs(row: dict | None) -> dict:
    if not row:
        return {"commentary_ids": [], "market_signal_ids": []}
    refs = row.get("audit_refs") or {}
    return {
        "commentary_ids": sorted(str(item) for item in refs.get("commentary_ids") or [] if item),
        "market_signal_ids": sorted(str(item) for item in refs.get("market_signal_ids") or [] if item),
    }


def _flags(relation_summary: dict, signal_summary: dict, has_relation: bool, has_signal: bool) -> list[str]:
    flags = []
    if relation_summary["cites_basis_out"] or relation_summary["cites_basis_in"]:
        flags.append("has_basis_chain")
    if relation_summary["references_out"] or relation_summary["references_in"]:
        flags.append("has_references")
    if relation_summary["supersedes_out"]:
        flags.append("supersedes_policy")
    if relation_summary["superseded_by_count"]:
        flags.append("superseded_by_policy")
    if relation_summary["clarifies_out"] or relation_summary["clarified_by_count"]:
        flags.append("has_clarification")

    attention = signal_summary["commentary_attention"]
    validation = signal_summary["market_validation"]
    certainty = signal_summary["certainty_adjustment"]
    commentary_count = signal_summary["commentary_signal_count"]
    market_count = signal_summary["market_signal_count"]
    if commentary_count and attention in {"medium", "high"}:
        flags.append(f"commentary_attention_{attention}")
    if market_count and validation in {"weak", "medium", "strong"}:
        flags.append(f"market_validation_{validation}")
    if commentary_count and market_count == 0:
        flags.append("no_market_validation")
    if certainty in {"lower", "raise"}:
        flags.append(f"certainty_{certainty}")
    if has_relation and not has_signal:
        flags.append("relation_only_no_signal_context")
    if has_signal and not has_relation:
        flags.append("signal_only_no_relation_context")
    return flags


def _build_rows(relations: list[dict], policy_context_rows: list[dict]) -> list[dict]:
    relation_by_policy, relation_refs = _aggregate_relations(relations)
    signal_by_policy = {
        str(row.get("policy_id") or ""): row
        for row in policy_context_rows
        if row.get("policy_id")
    }
    rows = []
    for policy_id in sorted(set(relation_by_policy) | set(signal_by_policy)):
        relation_summary = relation_by_policy.get(policy_id, _empty_relation_summary())
        signal_row = signal_by_policy.get(policy_id)
        signal_summary = _signal_summary(signal_row)
        signal_refs = _signal_audit_refs(signal_row)
        has_relation = policy_id in relation_by_policy
        has_signal = policy_id in signal_by_policy
        audit_refs = _empty_audit_refs()
        audit_refs["relation_candidate_ids"] = sorted(relation_refs.get(policy_id, set()))
        audit_refs["commentary_ids"] = signal_refs["commentary_ids"]
        audit_refs["market_signal_ids"] = signal_refs["market_signal_ids"]
        rows.append(
            {
                "policy_id": policy_id,
                "relation_summary": relation_summary,
                "signal_summary": signal_summary,
                "analysis_flags": _flags(relation_summary, signal_summary, has_relation, has_signal),
                "audit_refs": audit_refs,
            }
        )
    return rows


def _summary(relations: list[dict], policy_context_rows: list[dict], rows: list[dict]) -> dict:
    flag_counter = Counter(flag for row in rows for flag in row.get("analysis_flags") or [])
    rel_counter = Counter(str(row.get("rel") or "") for row in relations if row.get("rel"))
    rows_with_relation = sum(1 for row in rows if row["audit_refs"]["relation_candidate_ids"])
    rows_with_signal = sum(
        1
        for row in rows
        if row["signal_summary"]["commentary_signal_count"] or row["signal_summary"]["market_signal_count"]
    )
    return {
        "relation_candidate_count": len(relations),
        "policy_context_count": len(policy_context_rows),
        "analysis_context_count": len(rows),
        "rows_with_relation_context": rows_with_relation,
        "rows_with_signal_context": rows_with_signal,
        "rows_with_both": sum(
            1
            for row in rows
            if row["audit_refs"]["relation_candidate_ids"]
            and (
                row["signal_summary"]["commentary_signal_count"]
                or row["signal_summary"]["market_signal_count"]
            )
        ),
        "rows_by_flag": dict(sorted(flag_counter.items())),
        "rel_vocabulary_seen": dict(sorted(rel_counter.items())),
        "notes": [
            "preview_only_no_vault_write",
            "raw_unchanged",
            "no_model_call",
            "does_not_consume_review_queue_or_blocked_signals",
            "not_final_business_insight",
            "consumer_reads_analysis_context_not_raw_relations_or_signals",
        ],
    }


def run_preview(relations_path: Path, policy_context_path: Path, state: Path) -> dict:
    relations = _load_jsonl(relations_path)
    policy_context_rows = _load_jsonl(policy_context_path)
    rows = _build_rows(relations, policy_context_rows)
    summary = _summary(relations, policy_context_rows, rows)

    _write_jsonl(state / "analysis_context.jsonl", rows)
    _write_json(state / "analysis_context_summary.json", summary)
    report_path = render_preview_html(summary, rows, state / "reports" / "analysis_context_preview.html")
    return {
        "summary": summary,
        "analysis_context_path": str(state / "analysis_context.jsonl"),
        "summary_path": str(state / "analysis_context_summary.json"),
        "report_path": str(report_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--relations", type=Path, required=True)
    preview.add_argument("--policy-context", type=Path, required=True)
    preview.add_argument("--state", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.mode == "preview":
        result = run_preview(args.relations, args.policy_context, args.state)
    else:
        raise SystemExit(f"unsupported mode: {args.mode}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
