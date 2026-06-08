from scripts.l1_collect.channel_discovery import _institution_match


def _t(prov, ctype, level="省", city_code=""):
    return {"province": prov, "channel_type": ctype, "level": level, "city_code": city_code}


def test_real_province_sites_pass_by_area():
    assert _institution_match("zcom.zj.gov.cn", _t("浙江省", "商务"))          # zj 省段
    assert _institution_match("sxdofcom.shaanxi.gov.cn", _t("陕西省", "市监"))  # shaanxi 省段
    assert _institution_match("commerce.ah.gov.cn", _t("安徽省", "商务"))       # ah 省段


def test_real_city_site_pass_by_city_token():
    # 东莞市商务局(加油线市级 441900)→ dg 市段
    assert _institution_match("dgboc.dg.gov.cn", _t("广东省", "商务", "市", "441900"))


def test_marker_still_passes_when_area_absent():
    assert _institution_match("swt.fujian.gov.cn", _t("福建省", "商务"))        # fujian 段+swt marker


def test_cross_institution_rejected():
    assert not _institution_match("hq.mof.gov.cn", _t("海南省", "商务"))         # 财政部·非海南段
    assert not _institution_match("conghua.gov.cn", _t("广东省", "商务"))        # 从化区·无 gd 段无 marker


def test_non_commerce_market_type_passes():
    assert _institution_match("anything.gov.cn", _t("浙江省", "发改委"))         # 非商务/市监→True
