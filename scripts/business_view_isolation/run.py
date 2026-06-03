from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from .inventory import inventory_business_views, summarize
from .report import render_apply_html, render_html


DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"


def run_dryrun(vault: Path, state: Path) -> dict:
    decisions = inventory_business_views(vault)
    summary = summarize(decisions)
    state.mkdir(parents=True, exist_ok=True)

    manifest_path = state / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for decision in decisions:
            f.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")

    summary_path = state / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = render_html(decisions, summary, state / "reports" / "business_view_isolation.html")
    return {
        "summary": summary,
        "manifest_path": str(manifest_path),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_apply(vault: Path, state: Path, backup_dir: Path) -> dict:
    if _is_relative_to(backup_dir, vault):
        raise ValueError("backup_dir must be outside vault")

    manifest_path = state / "manifest.jsonl"
    rows = _load_manifest(manifest_path)
    apply_rows = []
    summary = {
        "applied": 0,
        "already_isolated": 0,
        "skipped_keep_current": 0,
        "skipped_manual_review": 0,
    }

    for row in rows:
        action = row.get("action")
        if action == "keep_current":
            summary["skipped_keep_current"] += 1
            continue
        if action != "isolate_legacy":
            summary["skipped_manual_review"] += 1
            continue

        rel = Path(row["path"])
        source = vault / rel
        backup = backup_dir / rel
        expected_sha = row["sha256"]

        if not source.exists():
            if backup.exists() and _sha256(backup) == expected_sha:
                status = "already_isolated"
                summary["already_isolated"] += 1
            else:
                raise FileNotFoundError(f"source missing and backup not verified: {source}")
        else:
            actual_sha = _sha256(source)
            if actual_sha != expected_sha:
                raise ValueError(f"source sha mismatch for {source}: {actual_sha} != {expected_sha}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            if backup.exists() and _sha256(backup) != expected_sha:
                raise ValueError(f"backup exists with different sha: {backup}")
            shutil.copy2(source, backup)
            if _sha256(backup) != expected_sha:
                raise ValueError(f"backup sha mismatch for {backup}")
            source.unlink()
            status = "applied"
            summary["applied"] += 1

        apply_rows.append({
            "pid": row["pid"],
            "path": row["path"],
            "backup_path": str(backup),
            "sha256": expected_sha,
            "status": status,
            "reasons": row.get("reasons", []),
        })

    apply_log = state / "apply_log.jsonl"
    with apply_log.open("w", encoding="utf-8") as f:
        for row in apply_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    apply_summary = state / "apply_summary.json"
    apply_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    apply_report = render_apply_html(apply_rows, summary, state / "reports" / "business_view_isolation_apply.html")
    return {
        "summary": summary,
        "apply_log": str(apply_log),
        "apply_summary": str(apply_summary),
        "apply_report": str(apply_report),
        "backup_dir": str(backup_dir),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    dry = sub.add_parser("dry-run")
    dry.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    dry.add_argument("--state", type=Path, required=True)
    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    apply_p.add_argument("--state", type=Path, required=True)
    apply_p.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.mode == "dry-run":
        result = run_dryrun(args.vault, args.state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.mode == "apply":
        result = run_apply(args.vault, args.state, args.backup_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
