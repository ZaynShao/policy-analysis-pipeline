from __future__ import annotations

import argparse
import json
from pathlib import Path

from .inventory import inventory_business_views, summarize
from .report import render_html


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
