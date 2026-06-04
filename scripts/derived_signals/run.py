from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import render_apply_html, render_preview_html


COMMENTARY_TARGET = Path("1_extracted/commentary_signals.jsonl")
MARKET_TARGET = Path("1_extracted/market_intel_signals.jsonl")
EXTRACTED_BY = "scripts/derived_signals/run.py"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prefixed(prefix: str, value: object) -> str:
    text = str(value or "")
    if text.startswith("0_raw/"):
        return text
    return f"{prefix}/{text}" if text else prefix


def _normalize_commentary(row: dict) -> dict:
    normalized = dict(row)
    normalized["schema_version"] = 1
    normalized["source_kind"] = "commentary"
    normalized["sanitized_from"] = _prefixed("0_raw/commentaries", row.get("path"))
    normalized["extracted_by"] = EXTRACTED_BY
    return normalized


def _normalize_market(row: dict) -> dict:
    normalized = dict(row)
    normalized["schema_version"] = 1
    normalized["source_kind"] = "market_intel"
    normalized["sanitized_from"] = _prefixed("0_raw/policies", row.get("raw_path"))
    normalized["extracted_by"] = EXTRACTED_BY
    return normalized


def _commentary_queue_index(queue: list[dict]) -> dict[str, list[str]]:
    index: dict[str, set[str]] = {}
    for row in queue:
        key = str(row.get("commentary_id") or "")
        if not key:
            continue
        index.setdefault(key, set()).add(str(row.get("reason") or "manual_review"))
    return {key: sorted(reasons) for key, reasons in index.items()}


def _market_block_key(row: dict) -> str:
    return "|".join(str(row.get(field) or "") for field in ["source_pid", "current_policy_id", "raw_path"])


def _market_match_keys(row: dict) -> set[str]:
    keys = set()
    for field in ["source_pid", "current_policy_id", "raw_path", "market_signal_id"]:
        value = str(row.get(field) or "")
        if value:
            keys.add(f"{field}:{value}")
    composite = _market_block_key(row)
    if composite.strip("|"):
        keys.add(f"composite:{composite}")
    return keys


def _market_queue_index(queue: list[dict]) -> tuple[dict[str, list[str]], dict[str, dict]]:
    reasons: dict[str, set[str]] = {}
    rows_by_key: dict[str, dict] = {}
    for row in queue:
        primary_key = _market_block_key(row)
        if not primary_key.strip("|"):
            primary_key = str(row.get("source_pid") or row.get("current_policy_id") or row.get("raw_path") or "")
        if not primary_key:
            continue
        rows_by_key.setdefault(primary_key, row)
        reasons.setdefault(primary_key, set()).add(str(row.get("reason") or "manual_review"))
        for match_key in _market_match_keys(row):
            rows_by_key.setdefault(match_key, row)
            reasons.setdefault(match_key, set()).add(str(row.get("reason") or "manual_review"))
    return {key: sorted(value) for key, value in reasons.items()}, rows_by_key


def _blocked_row(source_kind: str, block_key: str, row: dict, reasons: list[str]) -> dict:
    blocked = dict(row)
    blocked["source_kind"] = source_kind
    blocked["block_key"] = block_key
    blocked["queue_reasons"] = reasons
    blocked["publish_status"] = "blocked_pending_review"
    return blocked


def build_preview(commentary_state: Path, market_state: Path, state: Path) -> dict:
    commentary_queue = _load_jsonl(commentary_state / "review_queue.jsonl")
    market_queue = _load_jsonl(market_state / "review_queue.jsonl")
    commentary_queue_index = _commentary_queue_index(commentary_queue)
    market_queue_index, _ = _market_queue_index(market_queue)

    commentary_rows = []
    market_rows = []
    blocked_rows = []
    for row in _load_jsonl(commentary_state / "signals.jsonl"):
        key = str(row.get("commentary_id") or "")
        if key in commentary_queue_index:
            blocked_rows.append(_blocked_row("commentary", key, _normalize_commentary(row), commentary_queue_index[key]))
            continue
        commentary_rows.append(_normalize_commentary(row))

    for row in _load_jsonl(market_state / "market_signals.jsonl"):
        match_keys = _market_match_keys(row)
        matched = sorted(key for key in match_keys if key in market_queue_index)
        if matched:
            block_key = _market_block_key(row)
            reasons = sorted({reason for key in matched for reason in market_queue_index[key]})
            blocked_rows.append(_blocked_row("market_intel", block_key, _normalize_market(row), reasons))
            continue
        market_rows.append(_normalize_market(row))

    summary = {
        "source_commentary_state": str(commentary_state),
        "source_market_state": str(market_state),
        "candidate_commentary_signals": len(commentary_rows) + len([row for row in blocked_rows if row["source_kind"] == "commentary"]),
        "candidate_market_intel_signals": len(market_rows) + len([row for row in blocked_rows if row["source_kind"] == "market_intel"]),
        "commentary_signals": len(commentary_rows),
        "market_intel_signals": len(market_rows),
        "commentary_review_queue": len(commentary_queue),
        "market_intel_review_queue": len(market_queue),
        "blocked_commentary_signals": len([row for row in blocked_rows if row["source_kind"] == "commentary"]),
        "blocked_market_intel_signals": len([row for row in blocked_rows if row["source_kind"] == "market_intel"]),
        "blocked_signals": len(blocked_rows),
        "will_write": [str(COMMENTARY_TARGET), str(MARKET_TARGET)],
        "notes": [
            "preview_only_no_vault_write",
            "review_queue_blocks_publish",
            "apply_must_read_preview_outputs_only",
        ],
    }

    _write_jsonl(state / "commentary_signals.jsonl", commentary_rows)
    _write_jsonl(state / "market_intel_signals.jsonl", market_rows)
    _write_jsonl(state / "blocked_signals.jsonl", blocked_rows)
    _write_json(state / "summary.json", summary)
    report_path = render_preview_html(
        summary,
        commentary_rows,
        market_rows,
        blocked_rows,
        state / "reports" / "derived_signals_preview.html",
    )
    return {
        "summary": summary,
        "commentary_signals_path": str(state / "commentary_signals.jsonl"),
        "market_intel_signals_path": str(state / "market_intel_signals.jsonl"),
        "summary_path": str(state / "summary.json"),
        "report_path": str(report_path),
    }


def _target_in_extracted(target: Path) -> None:
    parts = target.parts
    if not parts or parts[0] != "1_extracted" or ".." in parts:
        raise ValueError(f"apply target must be under 1_extracted: {target}")


def _copy_preview_file(preview_state: Path, vault: Path, source_name: str, target: Path) -> dict:
    _target_in_extracted(target)
    source = preview_state / source_name
    if not source.exists():
        raise FileNotFoundError(source)
    destination = vault / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    destination.write_text(text, encoding="utf-8")
    return {
        "action": "write_whole_file",
        "source": str(source),
        "target": str(target),
        "rows": len([line for line in text.splitlines() if line.strip()]),
    }


def apply_preview(vault: Path, preview_state: Path) -> dict:
    commentary_rows = _load_jsonl(preview_state / "commentary_signals.jsonl")
    market_rows = _load_jsonl(preview_state / "market_intel_signals.jsonl")
    log_rows = [
        _copy_preview_file(preview_state, vault, "commentary_signals.jsonl", COMMENTARY_TARGET),
        _copy_preview_file(preview_state, vault, "market_intel_signals.jsonl", MARKET_TARGET),
    ]
    summary = {
        "written": [str(COMMENTARY_TARGET), str(MARKET_TARGET)],
        "commentary_signals": len(commentary_rows),
        "market_intel_signals": len(market_rows),
        "raw_writes": 0,
        "source_preview_state": str(preview_state),
    }
    _write_json(preview_state / "apply_summary.json", summary)
    _write_jsonl(preview_state / "apply_log.jsonl", log_rows)
    report_path = render_apply_html(summary, preview_state / "reports" / "derived_signals_apply.html")
    return {
        "summary": summary,
        "apply_summary_path": str(preview_state / "apply_summary.json"),
        "apply_log_path": str(preview_state / "apply_log.jsonl"),
        "report_path": str(report_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--commentary-state", type=Path, required=True)
    preview.add_argument("--market-state", type=Path, required=True)
    preview.add_argument("--state", type=Path, required=True)

    apply = sub.add_parser("apply")
    apply.add_argument("--vault", type=Path, required=True)
    apply.add_argument("--preview-state", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.mode == "preview":
        result = build_preview(args.commentary_state, args.market_state, args.state)
    elif args.mode == "apply":
        result = apply_preview(args.vault, args.preview_state)
    else:
        raise SystemExit(f"unsupported mode: {args.mode}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
