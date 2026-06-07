import json


def test_national_targets_cover_three_lines():
    from scripts.l1_collect.channel_discovery import NATIONAL_TARGETS
    domains = {t["root_domain"] for t in NATIONAL_TARGETS}
    assert {"ndrc.gov.cn", "nea.gov.cn", "miit.gov.cn", "www.gov.cn"} <= domains
    assert len(NATIONAL_TARGETS) >= 13


def test_province_targets_from_registry():
    from scripts.l1_collect.channel_discovery import province_targets_from_registry
    from pathlib import Path
    reg = Path.home() / "Documents/Zayn Main/政策分析/_meta/channel_registry.yaml"
    targets = province_targets_from_registry(reg)
    provs = {t["province"] for t in targets}
    for p in ("广东省", "江苏省", "浙江省", "四川省", "山东省"):
        assert p in provs


def test_pick_list_url_parses_llm_json():
    from scripts.l1_collect.channel_discovery import pick_list_url
    def fake_llm(system, user, max_tokens=512):
        return json.dumps({"list_url": "https://ndrc.gov.cn/zcfb/",
                           "confidence": 0.9, "reason": "政策发布栏目"})
    url = pick_list_url(
        target_name="国家发展和改革委员会",
        candidate_urls=["https://ndrc.gov.cn/zcfb/", "https://ndrc.gov.cn/news/"],
        llm_fn=fake_llm,
    )
    assert url == "https://ndrc.gov.cn/zcfb/"


def test_pick_list_url_none_when_no_candidates():
    from scripts.l1_collect.channel_discovery import pick_list_url
    assert pick_list_url("x", [], llm_fn=lambda s, u, **k: "{}") is None


def test_discover_builds_verified_channel(monkeypatch):
    """Tavily 给候选 → LLM 选 → probe ok → status=验证。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["https://ndrc.gov.cn/zcfb/"])
    monkeypatch.setattr(cd, "_llm_pick",
                        lambda name, urls: "https://ndrc.gov.cn/zcfb/")
    monkeypatch.setattr(cd, "probe_url",
                        lambda u, **k: ProbeResult(url=u, http_status=200,
                                                   page_has_list_pattern=True, verdict="ok"))
    ch = cd.discover_one({
        "city": "国家发展和改革委员会", "province": "国家", "level": "国家",
        "city_code": "000000", "channel_type": "发改委",
        "root_domain": "ndrc.gov.cn",
    })
    assert ch is not None
    assert ch.list_url == "https://ndrc.gov.cn/zcfb/"
    assert ch.status.value == "验证"


def test_same_domain_constraint():
    """域名约束：跨机构候选被判 False、同域(含子域)True。"""
    from scripts.l1_collect.channel_discovery import _same_domain
    assert _same_domain("https://www.ncsti.gov.cn/zcfg", "miit.gov.cn") is False
    assert _same_domain("https://www.miit.gov.cn/zcwj/", "miit.gov.cn") is True
    assert _same_domain("https://xxgk.mot.gov.cn/list.html", "mot.gov.cn") is True
    assert _same_domain("https://www.gov.cn/zhengce", "www.gov.cn") is True
    assert _same_domain("https://nhc.gov.cn/x", "www.gov.cn") is False


def test_discover_filters_cross_domain(monkeypatch):
    """Tavily 返回错机构 URL(ncsti) → 域名约束在 LLM 选之前过滤掉。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    seen = {}
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["https://www.ncsti.gov.cn/zcfg",
                                   "https://www.miit.gov.cn/zcwj/"])

    def fake_pick(name, urls):
        seen["urls"] = list(urls)
        return urls[0] if urls else None

    monkeypatch.setattr(cd, "_llm_pick", fake_pick)
    monkeypatch.setattr(cd, "probe_url",
                        lambda u, **k: ProbeResult(url=u, http_status=200,
                                                   page_has_list_pattern=True, verdict="ok"))
    ch = cd.discover_one({
        "city": "工业和信息化部", "province": "国家", "level": "国家",
        "city_code": "000000", "channel_type": "工信部", "root_domain": "miit.gov.cn",
    })
    assert seen["urls"] == ["https://www.miit.gov.cn/zcwj/"]  # ncsti 已被过滤
    assert "miit.gov.cn" in ch.list_url


def test_discover_tries_next_candidate_when_pick_probes_bad(monkeypatch):
    """LLM 选的 URL probe 不通(JS空壳) → 自动试同域其它候选,用第一个验证的。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["http://x.gov.cn/broken.htm", "http://x.gov.cn/good"])
    monkeypatch.setattr(cd, "_llm_pick", lambda name, urls: "http://x.gov.cn/broken.htm")

    def fake_probe(u, **k):
        ok = (u == "http://x.gov.cn/good")
        return ProbeResult(url=u, http_status=200, page_has_list_pattern=ok,
                           verdict="ok" if ok else "structure_unknown")

    monkeypatch.setattr(cd, "probe_url", fake_probe)
    ch = cd.discover_one({"city": "X", "province": "省X", "level": "省",
                          "city_code": "990000", "channel_type": "发改委",
                          "root_domain": "x.gov.cn"})
    assert ch.list_url == "http://x.gov.cn/good"  # 跳过 broken.htm 取能验证的
    assert ch.status.value == "验证"


def test_discover_keeps_pick_as_candidate_when_none_verify(monkeypatch):
    """所有同域候选都 probe 不通 → 保留 LLM 选的作候选(不空转到首页)。"""
    from scripts.l1_collect import channel_discovery as cd
    from scripts.l1_collect.connectivity_probe import ProbeResult
    monkeypatch.setattr(cd, "_tavily_search",
                        lambda q: ["http://x.gov.cn/a", "http://x.gov.cn/b"])
    monkeypatch.setattr(cd, "_llm_pick", lambda name, urls: "http://x.gov.cn/a")
    monkeypatch.setattr(cd, "probe_url",
                        lambda u, **k: ProbeResult(url=u, http_status=200,
                                                   page_has_list_pattern=False,
                                                   verdict="structure_unknown"))
    ch = cd.discover_one({"city": "X", "province": "省X", "level": "省",
                          "city_code": "990000", "channel_type": "发改委",
                          "root_domain": "x.gov.cn"})
    assert ch.list_url == "http://x.gov.cn/a"
    assert ch.status.value == "候选"


def test_commerce_market_targets_shape():
    from scripts.l1_collect.channel_discovery import commerce_market_targets
    targets = commerce_market_targets()
    by_type = {}
    for t in targets:
        by_type.setdefault(t["channel_type"], []).append(t)
    # 商务: 31 省 + 10 重点市 ; 市监: 31 省
    assert len(by_type["商务"]) == 31 + 10
    assert len(by_type["市监"]) == 31
    # 直辖市商务用"商务局"显示名,省用"商务厅"
    names = {t["city"] for t in by_type["商务"]}
    assert "江苏省商务厅" in names
    assert "北京市商务局" in names
    assert "佛山市商务局" in names          # 重点市(加油线)
    # 市监显示名
    assert "江苏省市场监督管理局" in {t["city"] for t in by_type["市监"]}
    # 省级目标 root_domain 默认 None(待发现);市监全 None
    assert all(t["root_domain"] is None for t in by_type["市监"])
    # 重点市 province = 所属省(非市名自身)
    dg = [t for t in by_type["商务"] if t["city"] == "东莞市商务局"][0]
    assert dg["province"] == "广东省"

def test_commerce_warmstart_from_registry(tmp_path):
    """registry 已有的商务域名 → root_domain 预填(暖启动)。"""
    from scripts.l1_collect.channel_discovery import commerce_market_targets
    reg = tmp_path / "reg.yaml"
    reg.write_text(
        "- domain: swt.fujian.gov.cn\n  issuer_canonical: 福建省商务厅\n",
        encoding="utf-8")
    targets = commerce_market_targets(registry_path=reg)
    fj = [t for t in targets if t["city"] == "福建省商务厅"][0]
    assert fj["root_domain"] == "swt.fujian.gov.cn"
