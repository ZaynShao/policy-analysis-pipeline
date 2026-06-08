"""ingester region 推断:省级渠道(city=省名/code末尾0000)不能被误标 level=市。"""
from scripts.l1_collect.ingester import _infer_region


def test_infer_region_province_from_code():
    r = _infer_region(None, "云南省", "530000")
    assert r["level"] == "省"
    assert r["name"] == "云南省"
    assert r["code"] == "530000"


def test_infer_region_city_keeps_市():
    r = _infer_region(None, "广州市", "440100")
    assert r["level"] == "市"
    assert r["name"] == "广州市"


def test_infer_region_national_by_code():
    r = _infer_region(None, "国家发展和改革委员会", "000000")
    assert r["level"] == "国家"
    assert r["name"] == "全国"


def test_infer_region_national_by_issuer_when_no_city():
    r = _infer_region("国家发展和改革委员会", None, None)
    assert r["level"] == "国家"


def test_infer_region_empty_when_unknown():
    r = _infer_region(None, None, None)
    assert r["level"] == ""
