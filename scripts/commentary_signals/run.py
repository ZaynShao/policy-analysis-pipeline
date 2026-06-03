from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import yaml

from .extractor import extract_commentary_signal, is_readable_body, parse_markdown, related_policy_ids
from .report import render_html


DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"


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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _summary(signals, queue: list[dict], counts: Counter) -> dict:
    return {
        "total_commentaries": counts["total_commentaries"],
        "linked_commentaries": counts["linked_commentaries"],
        "emitted_signals": len(signals),
        "review_queue": len(queue),
        "skipped_unlinked": counts["skipped_unlinked"],
        "skipped_not_policy_related": counts["skipped_not_policy_related"],
        "by_signal_role": dict(Counter(signal.signal_role for signal in signals)),
        "by_theme": dict(Counter(theme for signal in signals for theme in signal.theme_ids)),
    }


def run_dryrun(vault: Path, state: Path) -> dict:
    commentary_root = vault / "0_raw" / "commentaries"
    theme_aliases, theme_labels = load_theme_registry(vault / "_meta" / "themes_registry.yaml")
    state.mkdir(parents=True, exist_ok=True)

    counts = Counter()
    signals = []
    review_queue = []
    for path in sorted(commentary_root.glob("*.md")):
        counts["total_commentaries"] += 1
        doc = parse_markdown(path, commentary_root)
        policies = related_policy_ids(doc.frontmatter)

        if doc.frontmatter.get("not_policy_related") is True:
            counts["skipped_not_policy_related"] += 1
            continue
        if not policies:
            counts["skipped_unlinked"] += 1
            continue

        counts["linked_commentaries"] += 1
        signal = extract_commentary_signal(doc, theme_aliases)
        if signal is None:
            continue
        signals.append(signal)
        queue_reason = ""
        if not is_readable_body(doc.body):
            queue_reason = "linked_commentary_unreadable_body"
        elif not signal.theme_ids:
            queue_reason = "linked_commentary_without_theme_hit"
        if queue_reason:
            review_queue.append({
                "commentary_id": signal.commentary_id,
                "path": signal.path,
                "title": signal.title,
                "related_policy_ids": signal.related_policy_ids,
                "reason": queue_reason,
                "signal_role": signal.signal_role,
                "evidence": signal.evidence,
                "business_tag": signal.business_tag,
            })

    summary = _summary(signals, review_queue, counts)
    signals_path = state / "signals.jsonl"
    queue_path = state / "review_queue.jsonl"
    summary_path = state / "summary.json"
    report_path = state / "reports" / "commentary_signals_dryrun.html"
    _write_jsonl(signals_path, [signal.to_dict() for signal in signals])
    _write_jsonl(queue_path, review_queue)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_html(signals, review_queue, summary, theme_labels, report_path)
    return {
        "summary": summary,
        "signals_path": str(signals_path),
        "review_queue_path": str(queue_path),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    dry = sub.add_parser("dry-run")
    dry.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    dry.add_argument("--state", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.mode == "dry-run":
        result = run_dryrun(args.vault, args.state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
