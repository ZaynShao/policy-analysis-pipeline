from pathlib import Path
from scripts.l2_attribution.channel_registry import load_registry, lookup

FIX = Path(__file__).parent / "fixtures" / "channel_registry_min.yaml"


def test_load_indexes_by_domain():
    reg = load_registry(str(FIX))
    assert reg["www.jinan.gov.cn"].issuer_short == "SD"
    assert reg["www.ndrc.gov.cn"].region["level"] == "国家"


def test_lookup_extracts_host_from_url():
    reg = load_registry(str(FIX))
    e = lookup(reg, "https://www.jinan.gov.cn/col25768/art/2016/x.html")
    assert e is not None and e.issuer_short == "SD"


def test_lookup_unknown_domain_returns_none():
    reg = load_registry(str(FIX))
    assert lookup(reg, "https://solar.in-en.com/news/123.html") is None


def test_lookup_blank_url_returns_none():
    reg = load_registry(str(FIX))
    assert lookup(reg, "") is None
