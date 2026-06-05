from __future__ import annotations
from .models import SemanticCandidate, canonical_pair
from .loaders import PolicyView

TOP_K = 8
WINDOW_YEARS = 3
REGION_RANK = {"国": 3, "省": 2, "市": 1, "区": 0, "县": 0, "": 0}
EXTEND_WORDS = ("扩大", "扩围", "推广", "全面实施", "由试点", "适用范围", "新增")


def _rank(level: str) -> int:
    return REGION_RANK.get((level or "")[:1], 0)


def _window_ok(a: PolicyView, b: PolicyView) -> bool:
    return a.year is not None and b.year is not None and abs(a.year - b.year) <= WINDOW_YEARS


def _evidence(a: PolicyView, b: PolicyView, basis: list) -> dict:
    return {"from_title": a.title, "to_title": b.title,
            "from_window": "", "to_window": "",
            "theme_context": [a.primary_theme] if a.primary_theme else []}


def _similarity(a: PolicyView, b: PolicyView) -> float:
    """确定性相似:同 primary 主题(基线)+ 标题字符重合,用于 top-k 排序。"""
    base = 1.0 if a.primary_theme and a.primary_theme == b.primary_theme else 0.0
    sa, sb = set(a.title), set(b.title)
    jacc = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
    return base + jacc


def generate_candidates(views: dict, basis_pairs: set) -> list:
    items = list(views.values())
    out: list[SemanticCandidate] = []
    seen_symmetric: set = set()
    sym_degree: dict[str, int] = {}  # per-node degree cap for symmetric relations (§12)
    for a in items:
        if not a.primary_theme:
            continue
        scored = []  # (sim, b, rel, basis_tags)
        for b in items:
            if a.pid == b.pid or not b.primary_theme:
                continue
            same_theme = a.primary_theme == b.primary_theme
            # iterates: 同 issuer + 同主题 + 旧(a)→新(b)
            if same_theme and a.issuer and a.issuer == b.issuer and _window_ok(a, b) \
                    and a.year is not None and b.year is not None and a.year < b.year:
                scored.append((_similarity(a, b), b, "iterates", ["same_issuer", "same_theme", "year_increasing"]))
            # extends: 同主题 + 旧→新 + 新篇范围扩展词
            if same_theme and _window_ok(a, b) and a.year is not None and b.year is not None \
                    and a.year < b.year and any(w in b.title for w in EXTEND_WORDS):
                scored.append((_similarity(a, b), b, "extends", ["same_theme", "year_increasing", "scope_extend_word"]))
            # derives_from: ③-B basis 对 + from 区划低于 to + 主题同
            if (a.pid, b.pid) in basis_pairs and _rank(a.region_level) < _rank(b.region_level) and same_theme:
                scored.append((_similarity(a, b) + 2, b, "derives_from", ["basis_relation_present", "lower_region_level", "same_theme"]))
            # aligns_with: 同主题 + 跨地区/跨部门 + 窗内 + 无引用关系
            if same_theme and _window_ok(a, b) \
                    and (a.region_name != b.region_name or a.issuer != b.issuer) \
                    and (a.pid, b.pid) not in basis_pairs and (b.pid, a.pid) not in basis_pairs:
                scored.append((_similarity(a, b), b, "aligns_with", ["same_theme", "cross_region_or_dept"]))
        # §12 top-k(按 sim 降序,每源篇上限)
        scored.sort(key=lambda x: (-x[0], x[1].pid))
        kept = 0
        for sim, b, rel, tags in scored:
            if kept >= TOP_K:
                break
            if rel == "aligns_with":
                fp, tp = canonical_pair(a.pid, b.pid, rel)
                key = (fp, tp, rel)
                if key in seen_symmetric:
                    continue
                # §12: cap per-node degree for symmetric rels so no node exceeds TOP_K
                if sym_degree.get(fp, 0) >= TOP_K or sym_degree.get(tp, 0) >= TOP_K:
                    continue
                seen_symmetric.add(key)
                sym_degree[fp] = sym_degree.get(fp, 0) + 1
                sym_degree[tp] = sym_degree.get(tp, 0) + 1
                out.append(SemanticCandidate(fp, tp, rel, tags, _evidence(a, b, tags), symmetric=True))
            else:
                out.append(SemanticCandidate(a.pid, b.pid, rel, tags, _evidence(a, b, tags)))
            kept += 1
    return sorted(out, key=lambda c: (c.rel, c.from_id, c.to_id))
