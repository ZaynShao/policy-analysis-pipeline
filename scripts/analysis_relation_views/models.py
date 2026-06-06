"""③ 关系层视图投影器 — 共享词汇 + 出向→入向命名表(SCHEMA §5.2 / §5.3)。

canonical 边是 typed 有向边 (from, to, rel),由 ③-C(语义)+ ③-B(高精度)
合并而成。两视图都是它的单向投影:
  - API 视图 = relations_canonical.jsonl + _index_by_policy.json
  - OB 视图  = _rev_<pid>.md 反链页
"""
from __future__ import annotations

from dataclasses import dataclass, field

# SCHEMA §5.2 的 9 类关系出现顺序(也是反链页 section 渲染顺序)。
SECTION_ORDER = [
    "cites_basis",
    "supersedes",
    "iterates",
    "extends",
    "clarifies",
    "references",
    "aligns_with",
    "conflicts_with",
    "derives_from",
]

# SCHEMA §5.3「出向 → 入向命名表」。入向 = target 视角(被动式)。
REL_TO_INBOUND_LABEL = {
    "cites_basis": "被引为依据 (cited_as_basis_by)",
    "supersedes": "被废止 (superseded_by)",
    "iterates": "被迭代 (iterated_by)",
    "extends": "被扩展 (extended_by)",
    "clarifies": "被细化 (clarified_by)",
    "references": "被引用 (referenced_by)",
    "aligns_with": "被对齐 (aligns_with_by)",
    "conflicts_with": "被冲突 (conflicts_with_by)",
    "derives_from": "被落地 (landed_by)",
}

# 出向 = source 视角(主动式)。
REL_TO_OUTBOUND_LABEL = {
    "cites_basis": "引用为依据",
    "supersedes": "废止了",
    "iterates": "迭代了",
    "extends": "扩展了",
    "clarifies": "细化了",
    "references": "引用了",
    "aligns_with": "对齐了",
    "conflicts_with": "冲突于",
    "derives_from": "派生自",
}

VALID_RELS = frozenset(SECTION_ORDER)


@dataclass(frozen=True)
class RelEdge:
    """一条 canonical typed 有向边。"""

    from_id: str
    to_id: str
    rel: str
    confidence: float = 0.0
    evidence: str = ""
    source: str = ""  # 产出来源(③-B / ③-C 的 candidate_id 或脚本)

    @property
    def dedup_key(self) -> tuple[str, str, str]:
        """同 (from, to, rel) 视为同一条边,合并去重。"""
        return (self.from_id, self.to_id, self.rel)

    def to_row(self) -> dict:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "rel": self.rel,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "source": self.source,
        }
