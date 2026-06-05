"""③-C Task7 一次性:分层抽样 ~30 真实候选对 + 埋 ~10 错误,产出 golden 骨架。

确定性(无随机):按 sorted 候选列表 + 固定步长索引,相同输入 → 相同输出。
真实对标 is_planted=false, gold_decision="" (Task8 再标注)。
植入对标 is_planted=true, gold_decision="reject" (已知错误关系)。

用法:
    python3 -m scripts._oneshot.build_3c_golden \\
        --vault "/path/to/vault" \\
        --hpr state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl \\
        --out state/node3c/golden/golden_pairs.jsonl
"""
from __future__ import annotations
import sys, json, argparse
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.analysis_semantic_relations.loaders import load_policy_views, load_hpr_basis_pairs
from scripts.analysis_semantic_relations.candidates import generate_candidates

DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")
DEFAULT_HPR = "state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl"
DEFAULT_OUT = "state/node3c/golden/golden_pairs.jsonl"

REL_TYPES = ["derives_from", "extends", "iterates", "aligns_with"]
REAL_PER_REL = 8       # ≥5 per rel, pick 8 for headroom
EASY_CONFUSE_N = 3     # extra aligns_with pairs tagged as easy_confuse
PLANTED_FABRICATED = 5  # same-theme pairs with no real basis labeled derives_from
PLANTED_CONFUSED = 5    # real aligns_with pairs relabeled as derives_from


def _pick_diverse(cands_for_rel: list, n: int, stride: int = 1) -> list:
    """Deterministically pick n diverse candidates from sorted list.

    Diversity: round-robin over distinct from_id after sorting by (from_id, to_id).
    No randomness used.
    """
    # Group by from_id (sorted)
    by_from: dict[str, list] = defaultdict(list)
    for c in cands_for_rel:
        by_from[c.from_id].append(c)
    # Sort each group by to_id for stability
    groups = [sorted(v, key=lambda c: c.to_id) for k, v in sorted(by_from.items())]

    picked = []
    indices = [0] * len(groups)
    gi = 0
    while len(picked) < n:
        advanced = False
        for _ in range(len(groups)):
            gi_try = gi % len(groups)
            gi += 1
            g = groups[gi_try]
            idx = indices[gi_try]
            if idx < len(g):
                picked.append(g[idx])
                indices[gi_try] = idx + 1
                advanced = True
                if len(picked) >= n:
                    break
        if not advanced:
            break  # all groups exhausted
    return picked


def _to_golden_row(c, stratum: str, is_planted: bool,
                   planted_error_type: str | None, gold_decision: str,
                   override_rel: str | None = None) -> dict:
    rel = override_rel if override_rel is not None else c.rel
    return {
        "from": c.from_id,
        "to": c.to_id,
        "rel": rel,
        "stratum": stratum,
        "is_planted": is_planted,
        "planted_error_type": planted_error_type,
        "gold_decision": gold_decision,
        "from_title": c.evidence.get("from_title", ""),
        "to_title": c.evidence.get("to_title", ""),
        "from_window": c.evidence.get("from_window", ""),
        "to_window": c.evidence.get("to_window", ""),
        "candidate_basis": list(c.candidate_basis),
    }


def build(vault: str, hpr_path: str) -> list[dict]:
    views = load_policy_views(vault=vault)
    basis = load_hpr_basis_pairs(hpr_path)
    cands = generate_candidates(views, basis)

    # Group candidates by rel type, sorted for determinism
    by_rel: dict[str, list] = defaultdict(list)
    for c in cands:
        by_rel[c.rel].append(c)
    # Sort each group for full determinism
    for rel in by_rel:
        by_rel[rel].sort(key=lambda c: (c.from_id, c.to_id))

    rows: list[dict] = []
    used_keys: set[tuple] = set()  # (from, to, rel) to detect dups

    # --- Real pairs: 8 per rel type ---
    real_picks: dict[str, list] = {}
    for rel in REL_TYPES:
        pool = by_rel.get(rel, [])
        picked = _pick_diverse(pool, REAL_PER_REL)
        real_picks[rel] = picked
        for c in picked:
            key = (c.from_id, c.to_id, c.rel)
            used_keys.add(key)
            rows.append(_to_golden_row(c, stratum=rel, is_planted=False,
                                       planted_error_type=None, gold_decision=""))

    # --- Easy-confuse: extra aligns_with pairs tagged :easy_confuse ---
    # Pick aligns_with pairs not already used (same from-id as derives_from real picks
    # if possible, to highlight confusion risk)
    derives_from_pids = {c.from_id for c in real_picks.get("derives_from", [])}
    aligns_pool_ec = [c for c in by_rel.get("aligns_with", [])
                      if (c.from_id, c.to_id, c.rel) not in used_keys
                      and c.from_id in derives_from_pids]
    if len(aligns_pool_ec) < EASY_CONFUSE_N:
        # fallback: any unused aligns_with
        aligns_pool_ec = [c for c in by_rel.get("aligns_with", [])
                          if (c.from_id, c.to_id, c.rel) not in used_keys]
    ec_picked = _pick_diverse(aligns_pool_ec, EASY_CONFUSE_N)
    for c in ec_picked:
        key = (c.from_id, c.to_id, c.rel)
        used_keys.add(key)
        rows.append(_to_golden_row(c, stratum="aligns_with:easy_confuse", is_planted=False,
                                   planted_error_type=None, gold_decision=""))

    # --- Planted: fabricated_relation ---
    # Take real aligns_with pairs (no basis) but assert derives_from — genuinely wrong.
    # Use aligns_with pairs not yet used, picking from end of sorted list (furthest from
    # already picked for spread), relabeled as derives_from.
    aligns_unused = [c for c in reversed(by_rel.get("aligns_with", []))
                     if (c.from_id, c.to_id, c.rel) not in used_keys
                     and (c.from_id, c.to_id, "derives_from") not in used_keys]
    fabricated_picked = aligns_unused[:PLANTED_FABRICATED]
    for c in fabricated_picked:
        key = (c.from_id, c.to_id, "derives_from")
        used_keys.add(key)
        rows.append(_to_golden_row(c, stratum="planted", is_planted=True,
                                   planted_error_type="fabricated_relation",
                                   gold_decision="reject",
                                   override_rel="derives_from"))

    # --- Planted: aligns_as_derives confusion ---
    # Take fresh aligns_with pairs not used anywhere, relabel them derives_from.
    aligns_unused2 = [c for c in reversed(by_rel.get("aligns_with", []))
                      if (c.from_id, c.to_id, c.rel) not in used_keys
                      and (c.from_id, c.to_id, "derives_from") not in used_keys]
    confused_picked = aligns_unused2[:PLANTED_CONFUSED]
    for c in confused_picked:
        key = (c.from_id, c.to_id, "derives_from")
        used_keys.add(key)
        rows.append(_to_golden_row(c, stratum="planted", is_planted=True,
                                   planted_error_type="aligns_as_derives",
                                   gold_decision="reject",
                                   override_rel="derives_from"))

    return rows, views


def main():
    ap = argparse.ArgumentParser(description="③-C golden 分层抽样+埋错骨架")
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--hpr", default=DEFAULT_HPR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    rows, views = build(a.vault, a.hpr)

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Print distribution
    real_rows = [r for r in rows if not r["is_planted"]]
    planted_rows = [r for r in rows if r["is_planted"]]
    from collections import Counter
    rel_counts = Counter(r["rel"] for r in real_rows)
    stratum_counts = Counter(r["stratum"] for r in real_rows)
    planted_by_type = Counter(r["planted_error_type"] for r in planted_rows)

    print(f"\n输出: {a.out}")
    print(f"总计: {len(rows)} 行 (真实 {len(real_rows)} + 植入 {len(planted_rows)})")
    print("\n真实对按 rel 分布:")
    for rel in REL_TYPES:
        print(f"  {rel:20s}  {rel_counts.get(rel, 0)}")
    print("\n真实对按 stratum:")
    for s, n in sorted(stratum_counts.items()):
        print(f"  {s:30s}  {n}")
    print("\n植入错误按类型:")
    for t, n in planted_by_type.items():
        print(f"  {t:30s}  {n}")

    # Verify pids all in views
    all_pids = set(views.keys())
    bad = [(r["from"], r["to"]) for r in rows if r["from"] not in all_pids or r["to"] not in all_pids]
    if bad:
        print(f"\n⚠ {len(bad)} 行 pid 不在 views 中!")
    else:
        print("\n✓ 所有 pid 均在 views 中")


if __name__ == "__main__":
    main()
