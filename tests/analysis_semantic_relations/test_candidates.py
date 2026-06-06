from scripts.analysis_semantic_relations.loaders import PolicyView
from scripts.analysis_semantic_relations.candidates import (
    generate_candidates, TOP_K, WINDOW_YEARS, WINDOW_LEN,
)


def V(pid, year, theme, level="省", region="广东", issuer="发改委", title="方案", body=""):
    return PolicyView(pid=pid, title=title, region_level=level, region_name=region,
                      issuer=issuer, year=year, themes=[theme], primary_theme=theme,
                      importance=3, body=body)


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


def test_evidence_window_uses_body_anchor():
    """from_window/to_window 取正文锚点截段;无锚点则退回正文开头。"""
    body_with_anchor = "为贯彻落实国家某文件精神,现就本市新能源管理制定本方案。"
    body_no_anchor = "本方案旨在推进本市电力市场建设。"

    views = {
        "A": V("A", 2021, "power_market", region="广东", body=body_with_anchor),
        "B": V("B", 2021, "power_market", region="江苏", body=body_no_anchor),
    }
    cands = generate_candidates(views, basis_pairs=set())
    aligns = [c for c in cands if c.rel == "aligns_with"]
    assert len(aligns) == 1
    c = aligns[0]

    # from_window must be non-empty and contain an anchor substring
    assert c.evidence["from_window"], "from_window should be non-empty when body has anchor"
    assert "贯彻" in c.evidence["from_window"] or "落实" in c.evidence["from_window"]

    # to_window falls back to head (non-empty when body non-empty, no anchor)
    assert c.evidence["to_window"], "to_window should be non-empty when body is non-empty"
    assert c.evidence["to_window"] == body_no_anchor[:WINDOW_LEN].strip()


# 长正文:开头是点题句(主题),引用词"根据"在后面 → 拿来区分两种窗口策略
_LONG_BODY = ("广州市某某委员会通知。各有关单位:为进一步规范本市电动汽车充电设施的规划建设、"
              "运营管理工作。根据《国务院办公厅关于加快电动汽车充电基础设施建设的指导意见》"
              "(国办发〔2015〕73号)等有关文件,现制定本办法。")


def test_directed_window_anchors_on_citation():
    """有向关系(iterates/extends/derives_from)的窗口应锚在引用句,跳过开头套话。"""
    views = {
        "P1": V("P1", 2018, "power_market", issuer="发改委甲", body=_LONG_BODY),
        "P2": V("P2", 2021, "power_market", issuer="发改委甲", body="后续年度文件正文。"),
    }
    cands = generate_candidates(views, basis_pairs=set())
    it = [c for c in cands if c.rel == "iterates"]
    assert it, "应生成 iterates"
    fw = it[0].evidence["from_window"]
    assert fw.startswith("根据《国务院办公厅"), f"有向窗口应从引用句起头, got: {fw[:30]}"


def test_aligns_window_uses_head_not_citation():
    """aligns_with 不互引,窗口应取开头点题句(主题/范围),不得跳到引用列表。"""
    views = {
        "A": V("A", 2021, "power_market", region="广东", issuer="发改委甲", body=_LONG_BODY),
        "B": V("B", 2021, "power_market", region="江苏", issuer="发改委乙", body="江苏方案正文。"),
    }
    cands = generate_candidates(views, basis_pairs=set())
    aligns = [c for c in cands if c.rel == "aligns_with"]
    assert len(aligns) == 1
    # A 是字典序在前的 from
    fw = aligns[0].evidence["from_window"]
    assert fw.startswith("广州市某某委员会通知"), f"aligns 窗口应取正文开头, got: {fw[:30]}"
    assert "为进一步规范本市电动汽车充电设施" in fw, "aligns 窗口应含点题/范围句"


def test_aligns_evidence_matches_canonical_order():
    # P_Z sorts AFTER P_A lexicographically, so when the inner loop hits (a=P_Z, b=P_A)
    # canonical_pair swaps to (P_A, P_Z).  The bug: _evidence(a, b) is still built from
    # a=P_Z as "from" even though fp="P_A" is now from_id.  Distinct titles expose the swap.
    views = {
        "P_Z": PolicyView("P_Z", "ZED政策", "省", "江苏", "发改委甲", 2021,
                          ["power_market"], "power_market", 3),
        "P_A": PolicyView("P_A", "AYE政策", "省", "广东", "发改委乙", 2021,
                          ["power_market"], "power_market", 3),
    }
    cands = generate_candidates(views, basis_pairs=set())
    aligns = [c for c in cands if c.rel == "aligns_with"]
    assert len(aligns) == 1
    c = aligns[0]
    # Canonical order: P_A < P_Z lexicographically
    assert (c.from_id, c.to_id) == ("P_A", "P_Z"), f"expected ('P_A','P_Z'), got {(c.from_id, c.to_id)}"
    title_by_pid = {"P_A": "AYE政策", "P_Z": "ZED政策"}
    assert c.evidence["from_title"] == title_by_pid[c.from_id], (
        f"from_title '{c.evidence['from_title']}' does not match from_id '{c.from_id}'"
    )
    assert c.evidence["to_title"] == title_by_pid[c.to_id], (
        f"to_title '{c.evidence['to_title']}' does not match to_id '{c.to_id}'"
    )
