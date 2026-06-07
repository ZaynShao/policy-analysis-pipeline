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
                        lambda u: ProbeResult(url=u, http_status=200,
                                              page_has_list_pattern=True, verdict="ok"))
    ch = cd.discover_one({
        "city": "国家发展和改革委员会", "province": "国家", "level": "国家",
        "city_code": "000000", "channel_type": "发改委",
        "root_domain": "ndrc.gov.cn",
    })
    assert ch is not None
    assert ch.list_url == "https://ndrc.gov.cn/zcfb/"
    assert ch.status.value == "验证"
