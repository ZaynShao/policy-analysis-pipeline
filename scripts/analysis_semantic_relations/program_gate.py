from __future__ import annotations
from collections import defaultdict

WHITELIST = {"derives_from", "extends", "iterates", "aligns_with"}
REQUIRED = ("from", "to", "rel", "evidence", "candidate_basis")


def check_candidate_row(row: dict) -> list:
    viol = []
    for key in REQUIRED:
        if key not in row:
            viol.append(f"missing:{key}")
    if row.get("rel") not in WHITELIST:
        viol.append(f"rel_not_whitelisted:{row.get('rel')}")
    return viol


def partition_by_decision(candidates: list, judgments: dict) -> tuple:
    """judgments: candidate_id -> decision。返回 (accepted, manual)。
    只有 accept 进 accepted;manual_review/reject 进 manual;方向矛盾对降级 manual。"""
    accepted, manual = [], []
    for c in candidates:
        d = judgments.get(c["candidate_id"], "manual_review")
        (accepted if d == "accept" else manual).append(c)
    # 方向矛盾:同一对 pid(无序)在 accepted 里有 >1 种有向关系 → 全降级 manual
    by_pair = defaultdict(list)
    for c in accepted:
        by_pair[frozenset([c["from"], c["to"]])].append(c)
    conflicted = set()
    for pair, rows in by_pair.items():
        rels = {r["rel"] for r in rows if not r.get("symmetric")}
        if len(rels) > 1:
            conflicted.update(id(r) for r in rows if not r.get("symmetric"))
    if conflicted:
        keep, demote = [], []
        for c in accepted:
            (demote if id(c) in conflicted else keep).append(c)
        accepted, manual = keep, manual + demote
    return accepted, manual
