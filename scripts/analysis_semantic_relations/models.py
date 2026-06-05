from __future__ import annotations
import hashlib
from dataclasses import dataclass

SYMMETRIC = {"aligns_with", "conflicts_with"}
DIRECTED = {"derives_from", "extends", "iterates", "supersedes", "cites_basis", "references"}
SCHEMA_VERSION = "analysis_semantic_relation_preview.v1"


def canonical_pair(from_id: str, to_id: str, rel: str) -> tuple[str, str]:
    """对称关系按 pid 字典序规范化(§14);有向关系保留方向。"""
    if rel in SYMMETRIC and from_id > to_id:
        return to_id, from_id
    return from_id, to_id


def candidate_id(from_id: str, to_id: str, rel: str) -> str:
    raw = "|".join([from_id, to_id, rel])
    return "SRC_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SemanticCandidate:
    from_id: str
    to_id: str
    rel: str
    candidate_basis: list[str]          # ["basis_relation_present","same_theme",...]
    evidence: dict                       # {from_title,to_title,from_window,to_window,theme_context}
    symmetric: bool = False

    def cid(self) -> str:
        return candidate_id(self.from_id, self.to_id, self.rel)

    def to_row(self) -> dict:
        return {
            "candidate_id": self.cid(),
            "schema_version": SCHEMA_VERSION,
            "from": self.from_id, "to": self.to_id, "rel": self.rel,
            "symmetric": self.symmetric,
            "candidate_basis": list(self.candidate_basis),
            "evidence": self.evidence,
            "source": "scripts/analysis_semantic_relations/run.py",
        }


@dataclass(frozen=True)
class SemanticJudgment:
    candidate_id: str
    decision: str        # accept | reject | manual_review
    confidence: float
    reason: str
    model: str
