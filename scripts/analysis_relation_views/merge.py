"""canonical 合并器 — ③-C(语义)+ ③-B(高精度)→ 统一 typed 边集。

行为:
  - 读两源 jsonl(各自字段不同,归一到 RelEdge)
  - 过滤 dangling:端点 pid 不在当前 raw index → 剔(用代码判,不硬编 pid)
  - 去重:同 (from, to, rel) 合并为一条(保留较高 confidence 的那条)
  - rel 必须 ∈ VALID_RELS,否则计入 invalid(不静默发布)

输出 = API 视图原料:边集 + 按 pid 的邻接索引。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .models import RelEdge, VALID_RELS
from .raw_index import RawMeta


@dataclass
class MergeResult:
    edges: list[RelEdge]                       # 去重后的 canonical 边集
    dangling_dropped: int = 0                  # 端点不在 raw 被剔的边数
    invalid_rel_dropped: int = 0               # rel 不在白名单被剔
    duplicates_merged: int = 0                 # 同 (from,to,rel) 合并掉的重复
    source_counts: dict = field(default_factory=dict)   # 各源读入行数
    by_rel: dict = field(default_factory=dict)          # 去重后按 rel 计数


def _iter_jsonl(path: Path):
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def _edge_from_sem(row: dict) -> RelEdge:
    """③-C 语义关系行 → RelEdge。"""
    return RelEdge(
        from_id=row.get("from") or "",
        to_id=row.get("to") or "",
        rel=row.get("rel") or "",
        confidence=float(row.get("confidence") or 0.0),
        evidence=str(row.get("judge_reason") or ""),
        source=str(row.get("candidate_id") or "sem"),
    )


def _edge_from_hpr(row: dict) -> RelEdge:
    """③-B 高精度关系行 → RelEdge。"""
    return RelEdge(
        from_id=row.get("from") or "",
        to_id=row.get("to") or "",
        rel=row.get("rel") or "",
        confidence=float(row.get("confidence") or 0.0),
        evidence=str(row.get("evidence") or ""),
        source=str(row.get("candidate_id") or "hpr"),
    )


def merge_edges(
    sem_path: Path,
    hpr_path: Path,
    raw_index: dict[str, RawMeta],
) -> MergeResult:
    raw_pids = set(raw_index.keys())
    dangling = 0
    invalid = 0
    source_counts: dict[str, int] = {}

    # 先归一两源,再统一过滤 + 去重(保证两源同一条边也能合并)。
    raw_edges: list[RelEdge] = []
    sem_n = 0
    for row in _iter_jsonl(sem_path):
        sem_n += 1
        raw_edges.append(_edge_from_sem(row))
    source_counts["sem"] = sem_n

    hpr_n = 0
    for row in _iter_jsonl(hpr_path):
        hpr_n += 1
        raw_edges.append(_edge_from_hpr(row))
    source_counts["hpr"] = hpr_n

    by_key: dict[tuple[str, str, str], RelEdge] = {}
    dups = 0
    for e in raw_edges:
        if e.rel not in VALID_RELS:
            invalid += 1
            continue
        # dangling:from / to 任一不在当前 raw 即剔
        if e.from_id not in raw_pids or e.to_id not in raw_pids:
            dangling += 1
            continue
        prev = by_key.get(e.dedup_key)
        if prev is None:
            by_key[e.dedup_key] = e
        else:
            dups += 1
            # 保留 confidence 更高的(并合并证据 source 留痕)
            if e.confidence > prev.confidence:
                by_key[e.dedup_key] = e

    edges = list(by_key.values())
    by_rel = dict(Counter(e.rel for e in edges))
    return MergeResult(
        edges=edges,
        dangling_dropped=dangling,
        invalid_rel_dropped=invalid,
        duplicates_merged=dups,
        source_counts=source_counts,
        by_rel=by_rel,
    )


def build_adjacency(edges: list[RelEdge]) -> dict[str, dict]:
    """按 pid 的邻接索引(API 视图):{pid: {outbound:[...], inbound:[...]}}。

    服务器/前端读这个 + relations_canonical.jsonl,绝不 parse markdown。
    """
    idx: dict[str, dict] = defaultdict(lambda: {"outbound": [], "inbound": []})
    for e in edges:
        idx[e.from_id]["outbound"].append(
            {"to": e.to_id, "rel": e.rel, "confidence": e.confidence}
        )
        idx[e.to_id]["inbound"].append(
            {"from": e.from_id, "rel": e.rel, "confidence": e.confidence}
        )
    # 稳定排序,保证幂等
    for pid in idx:
        idx[pid]["outbound"].sort(key=lambda r: (r["rel"], r["to"]))
        idx[pid]["inbound"].sort(key=lambda r: (r["rel"], r["from"]))
    return dict(idx)
