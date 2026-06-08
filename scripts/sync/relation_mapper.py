"""relation 记录(dict) → PolicySemanticRelation 行 dict。纯函数。"""
from __future__ import annotations

VALID_RELATION_TYPES = (
    "derives_from", "extends", "iterates", "aligns_with", "cites_basis",
    "references", "clarifies", "supersedes", "conflicts_with",
)


def map_relation(rec: dict, pipeline_version: int) -> dict:
    rtype = rec.get("relation_type")
    if rtype not in VALID_RELATION_TYPES:
        raise ValueError(f"unknown relation_type: {rtype!r}")
    return {
        "from_pid": rec["from_pid"],
        "to_pid": rec["to_pid"],
        "relation_type": rtype,
        "confidence": rec.get("confidence"),
        "evidence": rec.get("evidence"),
        "pipeline_version": pipeline_version,
    }
