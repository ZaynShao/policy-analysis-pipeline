"""编排 ③ 关系层视图投影 — preview(只写 state/,绝不碰 vault)。

流程:
  1. 现读 raw → pid→{title,file_stem,date}(无缓存表)
  2. 合并 ③-C + ③-B → 过滤 dangling + 去重 → canonical 边集
  3. 写 API 视图(relations_canonical.jsonl + _index_by_policy.json)
  4. OB 投影 _rev_*.md(全量重生,带安全闸)

preview 产物全部落 state/node3c/relation_views_preview/(含 _index_by_policy 子目录,
满足 OB 投影器安全闸)。apply-to-vault **不在本模块**(由人另控)。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api_view import write_adjacency_index, write_canonical_jsonl
from .merge import merge_edges
from .ob_projector import project_pages
from .raw_index import load_raw_index

DEFAULT_VAULT = Path.home() / "Documents/Zayn Main/政策分析"


def run_preview(
    vault: Path,
    sem_path: Path,
    hpr_path: Path,
    out_root: Path,
) -> dict:
    raw_index = load_raw_index(vault)
    merged = merge_edges(sem_path, hpr_path, raw_index)

    # API 视图
    canonical_path = out_root / "relations_canonical.jsonl"
    adjacency_path = out_root / "_index_by_policy.json"
    write_canonical_jsonl(merged.edges, canonical_path)
    write_adjacency_index(merged.edges, adjacency_path)

    # OB 视图(目录名含 _index_by_policy 以满足投影器安全闸)
    ob_dir = out_root / "_index_by_policy"
    ob_stats = project_pages(merged.edges, raw_index, ob_dir)

    summary = {
        "mode": "preview",
        "raw_policies_indexed": len(raw_index),
        "source_rows": merged.source_counts,
        "dangling_dropped": merged.dangling_dropped,
        "invalid_rel_dropped": merged.invalid_rel_dropped,
        "duplicates_merged": merged.duplicates_merged,
        "canonical_edge_count": len(merged.edges),
        "canonical_by_relation": merged.by_rel,
        "rev_pages_written": ob_stats["pages_written"],
        "rev_pages_old_removed": ob_stats["old_removed"],
        "api_view_files": {
            "canonical_jsonl": str(canonical_path),
            "adjacency_index": str(adjacency_path),
        },
        "ob_view_dir": str(ob_dir),
        "notes": ["no_vault_write", "no_raw_write", "no_apply", "dangling_filtered"],
    }
    (out_root / "relation_views_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="③ 关系层视图投影器")
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("preview", help="只写 state/,不碰 vault")
    p.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    p.add_argument(
        "--sem",
        type=Path,
        default=Path("state/node3c/sem_preview_20260606/accepted_clean_final.jsonl"),
        help="③-C 语义关系 jsonl",
    )
    p.add_argument(
        "--hpr",
        type=Path,
        default=Path("state/node3c/hpr_873_2026-06-06/high_precision_relation_candidates.jsonl"),
        help="③-B 高精度关系 jsonl",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("state/node3c/relation_views_preview"),
    )
    args = ap.parse_args(argv)
    if args.mode == "preview":
        summary = run_preview(args.vault, args.sem, args.hpr, args.out)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
