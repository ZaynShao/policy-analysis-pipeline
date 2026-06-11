from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import yaml

from .extractor import build_policy_index, extract_market_signal, parse_policy_file
from .report import render_html


DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
DEFAULT_MANIFEST = Path("state/source_ready/market_intel_manifest.jsonl")


def load_theme_registry(path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    themes = (data or {}).get("themes") or []
    aliases = {}
    labels = {}
    for item in themes:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        theme_id = str(item["id"])
        zh = str(item.get("zh") or theme_id)
        labels[theme_id] = zh
        terms = [zh]
        terms.extend(str(a) for a in item.get("aliases") or [])
        aliases[theme_id] = terms
    return aliases, labels


def load_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _queue_reasons(signal) -> list[str]:
    reasons = []
    if not signal.theme_ids:
        reasons.append("theme_not_found")
    if not signal.region.get("name") or signal.region.get("name") == "未知":
        reasons.append("region_unknown")
    if not signal.observed_date:
        reasons.append("date_missing")
    if signal.signal_type == "unknown":
        reasons.append("signal_type_unknown")
    return reasons


def _summary(manifest_rows: list[dict], signals, queue: list[dict], located_raw: int) -> dict:
    return {
        "manifest_rows": len(manifest_rows),
        "located_raw": located_raw,
        "emitted_signals": len(signals),
        "review_queue": len(queue),
        "by_signal_type": dict(Counter(signal.signal_type for signal in signals)),
        "by_theme": dict(Counter(theme for signal in signals for theme in signal.theme_ids)),
        "by_business_line": dict(Counter(line for signal in signals for line in signal.business_lines)),
        "by_queue_reason": dict(Counter(row["reason"] for row in queue)),
    }


def run_dryrun(vault: Path, manifest: Path, state: Path) -> dict:
    policies_root = vault / "0_raw" / "policies"
    theme_aliases, theme_labels = load_theme_registry(vault / "_meta" / "themes_registry.yaml")
    rows = load_manifest(manifest)
    policy_index = build_policy_index(policies_root)
    signals = []
    queue = []
    located_raw = 0

    for row in rows:
        pid = str(row.get("pid") or "")
        raw_path = policy_index.get(pid)
        if raw_path is None:
            queue.append({
                "source_pid": pid,
                "title": row.get("title") or "",
                "reason": "manifest_pid_not_found",
                "evidence": "manifest PID not found in current 0_raw/policies id or aliases",
            })
            continue
        located_raw += 1
        doc = parse_policy_file(raw_path, policies_root)
        signal = extract_market_signal(row, doc, theme_aliases)
        signals.append(signal)
        for reason in _queue_reasons(signal):
            queue.append({
                "source_pid": signal.source_pid,
                "current_policy_id": signal.current_policy_id,
                "raw_path": signal.raw_path,
                "title": signal.title,
                "reason": reason,
                "evidence": signal.evidence,
            })

    summary = _summary(rows, signals, queue, located_raw)
    signals_path = state / "market_signals.jsonl"
    queue_path = state / "review_queue.jsonl"
    summary_path = state / "summary.json"
    report_path = state / "reports" / "market_intel_signals_dryrun.html"
    _write_jsonl(signals_path, [signal.to_dict() for signal in signals])
    _write_jsonl(queue_path, queue)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_html(signals, queue, summary, theme_labels, report_path)
    return {
        "summary": summary,
        "market_signals_path": str(signals_path),
        "review_queue_path": str(queue_path),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    dry = sub.add_parser("dry-run")
    dry.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    dry.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    dry.add_argument("--state", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.mode == "dry-run":
        result = run_dryrun(args.vault, args.manifest, args.state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
