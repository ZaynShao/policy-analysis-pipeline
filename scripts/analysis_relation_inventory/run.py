from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from .report import render_preview_html


HIGH_PRECISION_RELS = {"references", "cites_basis", "supersedes", "clarifies"}
SEMANTIC_LOW_CONFIDENCE_RELS = {"derives_from", "aligns_with", "extends"}
MIXED_PRECISION_RELS = {"iterates"}


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


def _parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return [_clean_scalar(value)] if value and value != "[]" else []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_clean_scalar(part) for part in inner.split(",") if _clean_scalar(part)]


def _frontmatter_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:idx]
    return []


def _parse_policy_frontmatter(path: Path) -> dict:
    lines = _frontmatter_lines(path)
    data = {"id": "", "aliases": [], "title": ""}
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            idx += 1
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if key == "id":
            data["id"] = _clean_scalar(value)
        elif key == "title":
            data["title"] = _clean_scalar(value)
        elif key == "aliases":
            if value:
                data["aliases"] = _parse_inline_list(value)
            else:
                aliases = []
                lookahead = idx + 1
                while lookahead < len(lines):
                    item = lines[lookahead].strip()
                    if item.startswith("- "):
                        aliases.append(_clean_scalar(item[2:]))
                        lookahead += 1
                        continue
                    break
                data["aliases"] = aliases
        idx += 1
    return data


def _build_policy_index(vault: Path, policy_files: list[Path]) -> dict[str, dict]:
    index = {}
    for path in policy_files:
        metadata = _parse_policy_frontmatter(path)
        policy_id = metadata.get("id") or ""
        rel_path = str(path.relative_to(vault))
        if policy_id:
            index[policy_id] = {
                "policy_id": policy_id,
                "path": rel_path,
                "title": metadata.get("title", ""),
                "matched_by": "id",
            }
        for alias in metadata.get("aliases") or []:
            if not alias or alias in index:
                continue
            index[alias] = {
                "policy_id": policy_id,
                "path": rel_path,
                "title": metadata.get("title", ""),
                "matched_by": "alias",
                "alias": alias,
            }
    return index


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_source_line"] = line_no
        rows.append(row)
    return rows


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _relation_files(vault: Path) -> list[Path]:
    relations_dir = vault / "1_extracted" / "relations"
    if not relations_dir.exists():
        return []
    return sorted(path for path in relations_dir.glob("*.jsonl") if path.is_file())


def _locate(policy_index: dict[str, dict], endpoint: object) -> tuple[str, dict]:
    endpoint_text = str(endpoint or "").strip()
    if not endpoint_text:
        return "empty", {}
    locator = policy_index.get(endpoint_text)
    if locator:
        return "located", locator
    return "missing", {}


def _relation_family_flags(rel: str) -> list[str]:
    if rel in HIGH_PRECISION_RELS:
        return ["high_precision_candidate"]
    if rel in SEMANTIC_LOW_CONFIDENCE_RELS:
        return ["semantic_low_confidence"]
    if rel in MIXED_PRECISION_RELS:
        return ["mixed_precision"]
    return ["unknown_relation_type"]


def _classify_row(path: Path, row: dict, policy_index: dict[str, dict]) -> dict:
    rel = str(row.get("rel") or path.stem)
    from_value = str(row.get("from") or "")
    to_value = str(row.get("to") or "")
    from_status, from_locator = _locate(policy_index, from_value)
    to_status, to_locator = _locate(policy_index, to_value)
    flags = []
    if path.name.startswith("_archive"):
        flags.append("archive_relation_file")
    if from_status == "empty":
        flags.append("from_empty")
    elif from_status == "missing":
        flags.append("from_missing")
    if to_status == "empty":
        flags.append("to_empty")
    elif to_status == "missing":
        flags.append("to_missing")
    if from_value.startswith("P_1900"):
        flags.append("from_p1900")
    if to_value.startswith("P_1900"):
        flags.append("to_p1900")
    flags.extend(_relation_family_flags(rel))
    return {
        "relation_file": path.name,
        "source_line": row.get("_source_line"),
        "rel": rel,
        "from": from_value,
        "to": to_value,
        "from_status": from_status,
        "to_status": to_status,
        "from_locator": from_locator,
        "to_locator": to_locator,
        "flags": flags,
        "confidence": row.get("confidence"),
        "evidence": row.get("evidence", ""),
        "source_row": {key: value for key, value in row.items() if key != "_source_line"},
    }


def _summarize(rows: list[dict], relation_file_counts: dict[str, int], tracked_count: int, untracked_count: int) -> dict:
    rows_by_relation = Counter(row["rel"] for row in rows)
    rows_by_flag = Counter(flag for row in rows for flag in row.get("flags", []))
    endpoint_missing_count = sum(
        1 for row in rows if row["from_status"] in {"missing", "empty"} or row["to_status"] in {"missing", "empty"}
    )
    archive_relation_rows = sum(1 for row in rows if "archive_relation_file" in row.get("flags", []))
    return {
        "tracked_policy_count": tracked_count,
        "untracked_policy_count": untracked_count,
        "relation_files": dict(sorted(relation_file_counts.items())),
        "relation_rows": len(rows),
        "rows_by_relation": dict(sorted(rows_by_relation.items())),
        "rows_by_flag": dict(sorted(rows_by_flag.items())),
        "endpoint_missing_count": endpoint_missing_count,
        "archive_relation_rows": archive_relation_rows,
        "recommendation": "audit_only_no_apply",
        "notes": [
            "read_only_no_vault_write",
            "raw_baseline_uses_git_tracked_files_only",
            "untracked_raw_excluded_from_baseline",
            "old_relation_rows_are_audit_inputs_not_new_analysis_outputs",
        ],
    }


def run_preview(vault: Path, state: Path) -> dict:
    tracked_policy_files = _tracked_policy_files(vault)
    untracked_policy_files = _untracked_policy_files(vault)
    policy_index = _build_policy_index(vault, tracked_policy_files)

    rows = []
    relation_file_counts = {}
    for relation_file in _relation_files(vault):
        raw_rows = _load_jsonl(relation_file)
        relation_file_counts[relation_file.name] = len(raw_rows)
        rows.extend(_classify_row(relation_file, row, policy_index) for row in raw_rows)

    summary = _summarize(rows, relation_file_counts, len(tracked_policy_files), len(untracked_policy_files))
    _write_json(state / "relation_inventory.json", summary)
    _write_jsonl(state / "relation_rows.jsonl", rows)
    report_path = render_preview_html(summary, rows, state / "reports" / "relation_inventory_preview.html")
    return {
        "summary": summary,
        "summary_path": str(state / "relation_inventory.json"),
        "relation_rows_path": str(state / "relation_rows.jsonl"),
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
