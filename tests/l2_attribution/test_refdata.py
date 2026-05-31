from scripts.l2_attribution.refdata import PROVINCE, MINISTRY, CITY_PROVINCE


def test_province_has_all_34_and_shape():
    assert len(PROVINCE) == 34
    sd = PROVINCE["山东省"]
    assert sd["issuer_short"] == "SD"
    assert sd["code2"] == "37"          # 山东省级码前两位


def test_municipality_code():
    assert PROVINCE["上海市"]["issuer_short"] == "SH"
    assert PROVINCE["上海市"]["code2"] == "31"


def test_ministry_map_ndrc():
    assert MINISTRY["www.ndrc.gov.cn"]["issuer_short"] == "NDRC"
    assert MINISTRY["www.ndrc.gov.cn"]["region"]["level"] == "国家"
    assert MINISTRY["www.ndrc.gov.cn"]["region"]["code"] == "000000"


def test_city_province_lookup():
    assert CITY_PROVINCE["济南市"] == "山东省"
    assert CITY_PROVINCE["苏州市"] == "江苏省"
