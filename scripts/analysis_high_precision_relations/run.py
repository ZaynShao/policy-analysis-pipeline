from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .report import render_preview_html


EXTRACTED_BY = "scripts/analysis_high_precision_relations/run.py"
RELATIONS = ["references", "cites_basis", "supersedes", "clarifies"]
BASIS_KEYWORDS = ["根据", "依据", "贯彻", "落实", "按照", "结合实际", "结合本"]
SUPERSEDES_KEYWORDS = ["同时废止", "同步废止", "即行废止", "废止", "停止执行", "失效"]
CLARIFIES_KEYWORDS = ["实施细则", "操作指引", "申报指南", "办事指南", "解读", "细则"]


@dataclass(frozen=True)
class PolicyDoc:
    policy_id: str
    title: str
    official_number: str
    path: str
    body: str


def _run_git(vault: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(vault), "-c", "core.quotePath=false", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _tracked_policy_files(vault: Path) -> list[Path]:
    return [vault / path for path in _run_git(vault, ["ls-files", "--", "0_raw/policies/*.md"])]


def _untracked_policy_files(vault: Path) -> list[Path]:
    return [
        vault / path
        for path in _run_git(vault, ["ls-files", "--others", "--exclude-standard", "--", "0_raw/policies/*.md"])
    ]


def _clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _split_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    closing = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = idx
            break
    if closing is None:
        return {}, text
    frontmatter = {}
    for line in lines[1:closing]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        if key.strip() in {"id", "title", "official_number"}:
            frontmatter[key.strip()] = _clean_scalar(raw_value)
    body = "\n".join(lines[closing + 1 :])
    return frontmatter, body


def _load_policy_docs(vault: Path, policy_files: list[Path]) -> list[PolicyDoc]:
    docs = []
    for path in policy_files:
        frontmatter, body = _split_markdown(path)
        policy_id = str(frontmatter.get("id") or "")
        if not policy_id:
            continue
        docs.append(
            PolicyDoc(
                policy_id=policy_id,
                title=str(frontmatter.get("title") or ""),
                official_number=_normalize_doc_number(frontmatter.get("official_number") or ""),
                path=str(path.relative_to(vault)),
                body=body,
            )
        )
    return docs


def _normalize_doc_number(value: str) -> str:
    return re.sub(r"\s+", "", _clean_scalar(str(value or "")))


def _doc_number_index(docs: list[PolicyDoc]) -> dict[str, list[PolicyDoc]]:
    index: dict[str, list[PolicyDoc]] = {}
    for doc in docs:
        if not doc.official_number:
            continue
        index.setdefault(doc.official_number, []).append(doc)
    return index


def _evidence_window(text: str, start: int, end: int, before: int = 80, after: int = 120) -> str:
    chunk = text[max(0, start - before) : min(len(text), end + after)]
    return re.sub(r"\s+", " ", chunk).strip()


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_supersedes(source_body: str, match_end: int, evidence: str) -> bool:
    after_doc_number = source_body[match_end : min(len(source_body), match_end + 60)]
    return _has_any(after_doc_number, SUPERSEDES_KEYWORDS) or _has_any(evidence[:120], ["即行废止", "同时废止", "同步废止"])


def _candidate_id(from_id: str, to_id: str, rel: str, doc_number: str) -> str:
    raw = "|".join([from_id, to_id, rel, doc_number])
    return "HPR_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _confidence(rel: str) -> float:
    return {
        "references": 0.72,
        "cites_basis": 0.9,
        "supersedes": 0.95,
        "clarifies": 0.86,
    }[rel]


def _make_candidate(
    *,
    source: PolicyDoc,
    target: PolicyDoc,
    rel: str,
    doc_number: str,
    evidence: str,
    location: str,
    rules: list[str],
) -> dict:
    return {
        "candidate_id": _candidate_id(source.policy_id, target.policy_id, rel, doc_number),
        "schema_version": "analysis_high_precision_relation_preview.v1",
        "from": source.policy_id,
        "to": target.policy_id,
        "rel": rel,
        "doc_number": doc_number,
        "evidence": evidence,
        "location": location,
        "confidence": _confidence(rel),
        "from_path": source.path,
        "to_path": target.path,
        "rules": rules,
        "extracted_by": EXTRACTED_BY,
    }


def _scan_candidates(docs: list[PolicyDoc], index: dict[str, list[PolicyDoc]]) -> list[dict]:
    candidates = []
    seen = set()
    for source in docs:
        compact_body = _normalize_doc_number(source.body)
        for doc_number, targets in index.items():
            start = compact_body.find(doc_number)
            if start < 0:
                continue
            end = start + len(doc_number)
            original_start = source.body.find(doc_number)
            if original_start >= 0:
                evidence = _evidence_window(source.body, original_start, original_start + len(doc_number))
                original_location = "opening" if original_start < 800 else "body"
                evidence_for_rules = evidence
            else:
                evidence = doc_number
                original_location = "opening" if start < 800 else "body"
                evidence_for_rules = source.body[:1000]
            for target in targets:
                if source.policy_id == target.policy_id:
                    continue
                rels = [("references", ["official_number_match"])]
                if original_location == "opening" and _has_any(evidence_for_rules, BASIS_KEYWORDS):
                    rels.append(("cites_basis", ["opening_doc_number_match", "basis_keyword"]))
                supersedes_match_end = original_start + len(doc_number) if original_start >= 0 else end
                if _is_supersedes(source.body, supersedes_match_end, evidence_for_rules):
                    rels.append(("supersedes", ["doc_number_match", "supersedes_keyword"]))
                if _has_any(source.title + evidence_for_rules, CLARIFIES_KEYWORDS):
                    rels.append(("clarifies", ["doc_number_match", "clarifies_keyword"]))
                for rel, rules in rels:
                    dedup_key = (source.policy_id, target.policy_id, rel, doc_number)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    candidates.append(
                        _make_candidate(
                            source=source,
                            target=target,
                            rel=rel,
                            doc_number=doc_number,
                            evidence=evidence,
                            location=original_location,
                            rules=rules,
                        )
                    )
    return sorted(candidates, key=lambda row: (row["rel"], row["from"], row["to"], row["doc_number"]))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _summary(
    *,
    tracked_policy_count: int,
    untracked_policy_count: int,
    official_number_targets: int,
    candidates: list[dict],
) -> dict:
    rows_by_relation = Counter(row["rel"] for row in candidates)
    return {
        "tracked_policy_count": tracked_policy_count,
        "untracked_policy_count": untracked_policy_count,
        "official_number_targets": official_number_targets,
        "candidate_count": len(candidates),
        "rows_by_relation": {rel: rows_by_relation.get(rel, 0) for rel in RELATIONS},
        "recommendation": "preview_only_no_apply",
        "notes": [
            "read_only_no_vault_write",
            "raw_baseline_uses_git_tracked_files_only",
            "untracked_raw_excluded_from_baseline",
            "no_model_call",
            "old_relations_not_used_as_accepted_input",
        ],
    }


def run_preview(vault: Path, state: Path) -> dict:
    tracked_policy_files = _tracked_policy_files(vault)
    untracked_policy_files = _untracked_policy_files(vault)
    docs = _load_policy_docs(vault, tracked_policy_files)
    index = _doc_number_index(docs)
    candidates = _scan_candidates(docs, index)
    summary = _summary(
        tracked_policy_count=len(tracked_policy_files),
        untracked_policy_count=len(untracked_policy_files),
        official_number_targets=len(index),
        candidates=candidates,
    )

    _write_json(state / "high_precision_relation_summary.json", summary)
    _write_jsonl(state / "high_precision_relation_candidates.jsonl", candidates)
    for rel in RELATIONS:
        _write_jsonl(
            state / "policy_relation_candidates" / f"{rel}.jsonl",
            [row for row in candidates if row["rel"] == rel],
        )
    report_path = render_preview_html(summary, candidates, state / "reports" / "high_precision_relation_preview.html")
    return {
        "summary": summary,
        "summary_path": str(state / "high_precision_relation_summary.json"),
        "candidates_path": str(state / "high_precision_relation_candidates.jsonl"),
        "report_path": str(report_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--vault", type=Path, required=True)
    preview.add_argument("--state", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.mode == "preview":
        result = run_preview(args.vault, args.state)
    else:
        raise SystemExit(f"unsupported mode: {args.mode}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
