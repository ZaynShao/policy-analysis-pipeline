from scripts.l2_attribution.models import ChannelEntry
from scripts.l2_attribution.resolver import resolve_identity, body_tail_of, old_hash_of


def _entry(**kw):
    base = dict(domain="www.jinan.gov.cn", issuer_short="SD",
                issuer_canonical="济南市人民政府",
                region={"level": "市", "code": "370100", "name": "济南市"})
    base.update(kw)
    return ChannelEntry(**base)


class FakeRec:
    def __init__(self, pid, title, url, date="", official_number="", path="/tmp/x.md"):
        self.pid, self.title, self.url = pid, title, url
        self.date, self.official_number, self.path = date, official_number, path


def test_old_hash_of():
    assert old_hash_of("P_2015_GO_af076ca3") == "af076ca3"
    assert old_hash_of("P_2024_NDRC_718") == "718"


def test_resolve_clean_city_writes_region_issuer_id(tmp_path):
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2015_GO_af076ca3",
                  "济南市人民政府办公厅关于加强成品油监管的通知",
                  "https://www.jinan.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="济南市人民政府办公厅\n2016年3月17日",
                          existing_ids=set())
    assert ri.fields["region"].value["name"] == "济南市"
    assert ri.fields["issuer"].value == ["济南市人民政府办公厅"]
    assert ri.fields["date"].value == "2016-03-17"
    assert ri.fields["id"].value == "P_2016_SD_af076ca3"
    assert not ri.has_conflicts()


def test_resolve_unknown_domain_all_queue():
    rec = FakeRec("P_2025_GO_x", "某标题", "https://solar.in-en.com/n.html")
    ri = resolve_identity(rec, {}, body_tail="", existing_ids=set())
    assert ri.has_conflicts()
    assert any(c.field == "_all" for c in ri.conflicts)
    assert not ri.fields


def test_resolve_title_domain_mismatch_queues_issuer():
    # 转载:标题机关"国务院办公厅"(国家) 与 域名承德(市) 不符 -> issuer 入队列,region 仍写
    reg = {"www.chengde.gov.cn": _entry(domain="www.chengde.gov.cn", issuer_short="HE",
            issuer_canonical="承德市人民政府",
            region={"level": "市", "code": "130800", "name": "承德市"})}
    rec = FakeRec("P_2025_GO_y",
                  "国务院办公厅关于推动成品油流通高质量发展的意见(转载)",
                  "https://www.chengde.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2025年1月1日", existing_ids=set())
    assert ri.fields["region"].value["name"] == "承德市"
    assert "issuer" not in ri.fields
    assert any(c.field == "issuer" for c in ri.conflicts)


def test_resolve_id_collision_suffix():
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2015_GO_af076ca3", "济南市人民政府办公厅关于X的通知",
                  "https://www.jinan.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2016年3月17日",
                          existing_ids={"P_2016_SD_af076ca3"})
    assert ri.fields["id"].value == "P_2016_SD_af076ca3_a"


def test_resolve_already_correct_id_is_noop():
    # pid 已是正确 P_<year>_SD_<hash>,且 existing_ids 含它自己 -> 不应重写 id
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2016_SD_af076ca3", "济南市人民政府办公厅关于X的通知",
                  "https://www.jinan.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2016年3月17日",
                          existing_ids={"P_2016_SD_af076ca3"})
    assert "id" not in ri.fields
    assert not any(c.field == "id" for c in ri.conflicts)


def test_resolve_national_level_issuer_backed():
    # 国家级域名 -> 标题机关无需地名匹配即被背书写入
    reg = {"www.ndrc.gov.cn": _entry(domain="www.ndrc.gov.cn", issuer_short="NDRC",
            issuer_canonical="国家发展和改革委员会",
            region={"level": "国家", "code": "000000", "name": "全国"})}
    rec = FakeRec("P_2024_GO_718",
                  "国家发展改革委办公厅关于促进大功率充电设施建设的通知",
                  "https://www.ndrc.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2024年5月1日", existing_ids=set())
    assert ri.fields["issuer"].value == ["国家发展改革委办公厅"]
    assert not any(c.field == "issuer" for c in ri.conflicts)


def test_resolve_title_without_issuer_skips_issuer_silently():
    # 标题无 "X关于" 机关前缀 -> 不写 issuer,也不入 issuer 冲突(保守:无信号无动作)
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2015_GO_af076ca3", "电力现货市场基本规则(试行)",
                  "https://www.jinan.gov.cn/x.html")
    ri = resolve_identity(rec, reg, body_tail="2016年3月17日", existing_ids=set())
    assert "issuer" not in ri.fields
    assert not any(c.field == "issuer" for c in ri.conflicts)
