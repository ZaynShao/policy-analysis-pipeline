from scripts.l2_attribution.seed_channel_registry import (
    parse_channel_md, derive_entry,
)

SAMPLE_MD = """## 中央政府（国家级）
| 根域名 | 渠道名称 |
| --- | --- |
| www.ndrc.gov.cn | 国家发展和改革委员会 |

## 地方政府
| 根域名 | 渠道名称 |
|--------|---------|
| www.jinan.gov.cn | 济南市人民政府 |
| fgw.sh.gov.cn | 上海市发展和改革委员会 |
"""


def test_parse_channel_md_yields_domain_name_pairs():
    pairs = parse_channel_md(SAMPLE_MD)
    assert ("www.jinan.gov.cn", "济南市人民政府") in pairs
    assert ("fgw.sh.gov.cn", "上海市发展和改革委员会") in pairs


def test_derive_ministry_domain():
    e = derive_entry("www.ndrc.gov.cn", "国家发展和改革委员会")
    assert e["issuer_short"] == "NDRC"
    assert e["region"]["level"] == "国家"


def test_derive_city_from_channel_name():
    # 渠道名称含"济南市" -> 市级,省级码 SD,code 省级回退 370000 + 待精化标记
    e = derive_entry("www.jinan.gov.cn", "济南市人民政府")
    assert e["issuer_short"] == "SD"
    assert e["region"]["level"] == "市"
    assert e["region"]["name"] == "济南市"


def test_derive_unknown_returns_none():
    assert derive_entry("solar.in-en.com", "某行业媒体") is None
    assert derive_entry("www.weirdcity.gov.cn", "未知地名办公室") is None


def test_derive_from_domain_province_abbrev():
    from scripts.l2_attribution.seed_channel_registry import derive_from_domain
    e = derive_from_domain("fgw.sh.gov.cn")
    assert e["issuer_short"] == "SH" and e["region"]["name"] == "上海市"


def test_derive_from_domain_province_fullpinyin():
    from scripts.l2_attribution.seed_channel_registry import derive_from_domain
    e = derive_from_domain("czt.fujian.gov.cn")
    assert e["issuer_short"] == "FJ" and e["region"]["level"] == "省"


def test_derive_from_domain_city():
    from scripts.l2_attribution.seed_channel_registry import derive_from_domain
    e = derive_from_domain("www.jinan.gov.cn")
    assert e["issuer_short"] == "SD" and e["region"]["name"] == "济南市"


def test_derive_from_domain_ministry_subdomain():
    from scripts.l2_attribution.seed_channel_registry import derive_from_domain
    assert derive_from_domain("dcj.mofcom.gov.cn")["issuer_short"] == "MOFCOM"
    assert derive_from_domain("www.gov.cn")["issuer_short"] == "GWY"


def test_derive_from_domain_unknown_none():
    from scripts.l2_attribution.seed_channel_registry import derive_from_domain
    assert derive_from_domain("solar.in-en.com") is None
