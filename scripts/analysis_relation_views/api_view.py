"""API/数据视图写出 — relations_canonical.jsonl + _index_by_policy.json。

服务器/前端读这两个结构化文件,绝不 parse markdown 双链(spec §10.6 消费契约)。
"""
from __future__ import annotations

import json
from pathlib import Path

from .merge import build_adjacency
from .models import RelEdge


def write_canonical_jsonl(edges: list[RelEdge], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 稳定排序,保证幂等
    rows = sorted(
        (e.to_row() for e in edges),
        key=lambda r: (r["from"], r["to"], r["rel"]),
    )
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_adjacency_index(edges: list[RelEdge], path: Path) -> None:
    idx = build_adjacency(edges)
    path.parent.mkdir(parents=True, exist_ok=True)
    # key 排序保证幂等
    ordered = {pid: idx[pid] for pid in sorted(idx)}
    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
