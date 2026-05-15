#!/usr/bin/env python3
"""
T3 Phase 1 · A1 archive

把 P_1900 inventory 里 is_a=true 的 28 篇(被 classifier 标为 news_or_press / index_page)
整体迁到 vault `0_raw/_archive/policies/t3_a1_classifier_drops_2026-05-08/`。

不修改 frontmatter,不动 body,follow 现有 _archive 子目录批次惯例
(参考 vault 内已有的 `p2_7_a1_drops_*` / `p0_refetch_drops_*` 批次)。

默认 dry-run,实跑要传 --apply。

派生层(business_view / relations / policy_summaries / 反链页 / 主题页)
中指向被 archive 的 28 个 P_1900_* id 的引用,**不**在本脚本处理,留独立 oneshot
扫描清理(避免一次 commit 跨 raw + 派生)。

用法:
    python3 scripts/_oneshot/t3_phase1_archive_a1.py             # dry-run
    python3 scripts/_oneshot/t3_phase1_archive_a1.py --apply     # 真跑
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
INVENTORY_DEFAULT = Path(__file__).resolve().parents[2] / "state" / "T3" / "p1900_inventory.jsonl"
BATCH_LABEL = "t3_a1_classifier_drops_2026-05-08"


def load_inventory(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--inventory", type=Path, default=INVENTORY_DEFAULT)
    ap.add_argument("--apply", action="store_true",
                    help="实跑(默认 dry-run)")
    args = ap.parse_args()

    if not args.inventory.exists():
        print(f"❌ inventory 文件不存在: {args.inventory}", file=sys.stderr)
        print("   先跑: python3 scripts/audit/dump_p1900_inventory.py", file=sys.stderr)
        sys.exit(2)

    rows = load_inventory(args.inventory)
    a_rows = [r for r in rows if r.get("is_a")]

    src_dir = args.vault / "0_raw" / "policies"
    dst_dir = args.vault / "0_raw" / "_archive" / "policies" / BATCH_LABEL

    print(f"vault: {args.vault}")
    print(f"src:   {src_dir}")
    print(f"dst:   {dst_dir}")
    print(f"模式:  {'APPLY (真跑)' if args.apply else 'DRY-RUN (不动数据)'}")
    print(f"待 archive: {len(a_rows)} 篇")
    print()

    missing, would_collide = [], []
    for r in a_rows:
        sp = src_dir / r["filename"]
        dp = dst_dir / r["filename"]
        if not sp.exists():
            missing.append(r["filename"])
        if dp.exists():
            would_collide.append(r["filename"])

    if missing:
        print(f"⚠️  源文件不存在 ({len(missing)} 篇,跳过):")
        for f in missing[:5]:
            print(f"    {f}")
        if len(missing) > 5:
            print(f"    ...({len(missing) - 5} more)")
        print()
    if would_collide:
        print(f"❌ 目标位置已有同名 ({len(would_collide)} 篇,需要人工查):")
        for f in would_collide[:5]:
            print(f"    {f}")
        if not args.apply:
            print("   dry-run 不阻塞,实跑会跳过冲突项")
        print()

    if args.apply:
        dst_dir.mkdir(parents=True, exist_ok=True)
        log = []
        ok, skipped = 0, 0
        for r in a_rows:
            sp = src_dir / r["filename"]
            dp = dst_dir / r["filename"]
            if not sp.exists() or dp.exists():
                skipped += 1
                continue
            shutil.move(str(sp), str(dp))
            log.append({
                "filename": r["filename"],
                "id": r["id"],
                "label": r["classification_label"],
                "moved_to": str(dp.relative_to(args.vault)),
            })
            ok += 1
        log_path = Path(__file__).resolve().parents[2] / "state" / "T3" / f"{BATCH_LABEL}_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"✓ 移动完成: {ok} 篇 / 跳过 {skipped} 篇")
        print(f"✓ 日志: {log_path}")
    else:
        for r in a_rows[:10]:
            print(f"  [{r['classification_label']}] {r['id']}")
            print(f"      {r['filename']}")
        if len(a_rows) > 10:
            print(f"  ... 还有 {len(a_rows) - 10} 篇")
        print()
        print("dry-run 完成。确认无误后传 --apply 真跑。")


if __name__ == "__main__":
    main()
