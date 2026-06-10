"""存量回扫:扫全量 policies/ 命中 commentary marker 的 → DRY 报告 → apply via route_files。
带审核门:DRY_RUN(默认)只出报告;APPLY=1 才转 commentaries/。tracked 走 git rm。
"""
from __future__ import annotations
import os
from pathlib import Path

from scripts.l1_collect.policy_gate import COMMENTARY_MARKERS
from scripts.l1_collect.route_interpretations import route_files, build_title_index, _front_body

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
POLICIES = VAULT / "0_raw/policies"
APPLY = os.environ.get("APPLY") == "1"


def detect_commentary(policies_dir: Path) -> list:
    hits = []
    for p in sorted(policies_dir.glob("*.md")):
        fm, _ = _front_body(p.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        if any(m in str(fm.get("title") or "") for m in COMMENTARY_MARKERS):
            hits.append(p)
    return hits


def pool_entries(hits: list) -> list:
    return [{"kind": "sweep", "ref": p.name,
             "reason": "title_commentary_marker", "suggested_action": "confirm",
             "confidence": None, "evidence": p.name[:80],
             "channel": "sweep", "run_label": "sweep"} for p in hits]


def main():
    hits = detect_commentary(POLICIES)
    print(f"存量 policies 命中 commentary marker: {len(hits)}  APPLY={APPLY}")
    for p in hits[:200]:
        print("  ", p.name[:70])
    from scripts.l1_collect import review_pool
    for e in pool_entries(hits):
        review_pool.append(e)
    idx = build_title_index(skip_paths={p.name for p in hits})
    n = route_files(hits, index=idx, dry=not APPLY)
    print(f"{'已转' if APPLY else '(dry)将转'} {n} → commentaries/")


if __name__ == "__main__":
    main()
