from scripts.analysis_semantic_relations.loaders import PolicyView
from scripts.analysis_semantic_relations.candidates import generate_candidates, TOP_K, WINDOW_YEARS


def V(pid, year, theme, level="省", region="广东", issuer="发改委", title="方案"):
    return PolicyView(pid=pid, title=title, region_level=level, region_name=region,
                      issuer=issuer, year=year, themes=[theme], primary_theme=theme,
                      importance=3)


def test_iterates_same_issuer_theme_year_increasing():
    views = {"P1": V("P1", 2020, "power_market"), "P2": V("P2", 2022, "power_market")}
    cands = generate_candidates(views, basis_pairs=set())
    iters = [c for c in cands if c.rel == "iterates"]
    assert any(c.from_id == "P1" and c.to_id == "P2" for c in iters)  # 旧→新


def test_aligns_requires_cross_region_symmetric_dedup():
    views = {"A": V("A", 2021, "power_market", region="广东"),
             "B": V("B", 2021, "power_market", region="江苏")}
    cands = generate_candidates(views, basis_pairs=set())
    aligns = [c for c in cands if c.rel == "aligns_with"]
    assert len(aligns) == 1                      # 对称去重:只一条
    assert aligns[0].symmetric is True
    assert (aligns[0].from_id, aligns[0].to_id) == ("A", "B")  # 字典序


def test_aligns_skipped_same_region():
    views = {"A": V("A", 2021, "power_market", region="广东", issuer="发改委"),
             "B": V("B", 2021, "power_market", region="广东", issuer="发改委")}
    cands = generate_candidates(views, basis_pairs=set())
    assert not [c for c in cands if c.rel == "aligns_with"]  # 同地区同部门→不生成 aligns


def test_derives_from_needs_basis_and_lower_region():
    views = {"LOCAL": V("LOCAL", 2022, "power_market", level="市", region="深圳"),
             "NAT": V("NAT", 2021, "power_market", level="国", region="全国", issuer="发改委")}
    # 有 basis 对(local 引 nat)→ derives_from local→nat
    cands = generate_candidates(views, basis_pairs={("LOCAL", "NAT")})
    assert any(c.rel == "derives_from" and c.from_id == "LOCAL" and c.to_id == "NAT" for c in cands)
    # 无 basis 对 → 不生成 derives_from
    assert not [c for c in generate_candidates(views, basis_pairs=set()) if c.rel == "derives_from"]


def test_window_caps_year_gap():
    views = {"P1": V("P1", 2010, "power_market"), "P2": V("P2", 2022, "power_market")}
    cands = generate_candidates(views, basis_pairs=set())
    assert not [c for c in cands if c.rel in {"iterates", "aligns_with"}]  # Δ=12 > 3


def test_topk_bound():
    base = {f"S{i}": V(f"S{i}", 2021, "power_market", region=f"r{i}") for i in range(20)}
    src = {"SRC": V("SRC", 2022, "power_market", region="rc")}
    cands = generate_candidates({**base, **src}, basis_pairs=set())
    from_src = [c for c in cands if c.from_id == "SRC" or c.to_id == "SRC"]
    aligns_touching_src = [c for c in from_src if c.rel == "aligns_with"]
    assert len(aligns_touching_src) <= TOP_K
