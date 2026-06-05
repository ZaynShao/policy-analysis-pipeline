from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
from .loaders import load_policy_views, load_hpr_basis_pairs
from .candidates import generate_candidates
from .judge import judge_candidate
from . import program_gate
from .report import render_preview_html


def _write_jsonl(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_preview(vault: Path, state: Path, hpr_path: Path, judge_client) -> dict:
    views = load_policy_views(vault=vault)
    basis = load_hpr_basis_pairs(hpr_path)
    candidates = [c.to_row() for c in generate_candidates(views, basis)]
    # 程序门:schema/白名单
    gate_fail = [c for c in candidates if program_gate.check_candidate_row(c)]
    valid = [c for c in candidates if not program_gate.check_candidate_row(c)]
    # 受限判定
    judgments = {}
    for c in valid:
        v = judge_candidate(judge_client, c)
        judgments[c["candidate_id"]] = v.decision
        c["confidence"] = v.confidence
        c["judge_reason"] = v.reason
        c["model"] = v.model
    accepted, manual = program_gate.partition_by_decision(valid, judgments)
    summary = {
        "candidate_count": len(candidates),
        "gate_failed": len(gate_fail),
        "accepted_count": len(accepted),
        "manual_count": len(manual),
        "accepted_by_relation": dict(Counter(c["rel"] for c in accepted)),
        "model": getattr(judge_client, "model", "unknown"),
        "recommendation": "preview_only_no_apply",
        "notes": ["no_vault_write", "no_raw_write", "no_apply",
                  "manual_review_not_in_accepted", "old_relations_not_used_as_accepted"],
    }
    _write_jsonl(state / "semantic_relation_candidates.jsonl", candidates)
    _write_jsonl(state / "accepted_semantic_relations.jsonl", accepted)
    _write_jsonl(state / "manual_review_queue.jsonl", manual)
    (state / "semantic_relation_summary.json").parent.mkdir(parents=True, exist_ok=True)
    (state / "semantic_relation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = render_preview_html(summary, accepted, manual, state / "reports" / "semantic_relation_preview.html")
    return {"summary": summary, "report_path": str(report)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("preview")
    p.add_argument("--vault", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--hpr", type=Path, required=True, help="③-B high_precision_relation_candidates.jsonl")
    p.add_argument("--judge-model", default="deepseek-v4-flash")
    args = ap.parse_args(argv)
    if args.mode == "preview":
        from scripts.common.llm import OpenAICompatClient
        client = OpenAICompatClient(model=args.judge_model,
                                    log_path=str(args.state / "judge_calls.jsonl"))
        res = run_preview(args.vault, args.state, args.hpr, client)
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
