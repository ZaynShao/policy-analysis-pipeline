from scripts.l2_attribution.models import ChannelEntry
from scripts.l2_attribution.resolver import resolve_identity, body_tail_of, old_hash_of


def _entry(**kw):
    base = dict(domain="www.jinan.gov.cn", issuer_short="SD",
                issuer_canonical="济南市人民政府",
                region={"level": "市", "code": "370100", "name": "济南市"})
    base.update(kw)
    return ChannelEntry(**base)


class FakeRec:
    def __init__(self, pid, title, url, date="", official_number="", path="/tmp/x.md",
                 raw_fm=None, issuer=None):
        self.pid, self.title, self.url = pid, title, url
        self.date, self.official_number, self.path = date, official_number, path
        self.raw_fm = raw_fm or {}
        self.issuer = issuer


def test_old_hash_of():
    assert old_hash_of("P_2015_GO_af076ca3") == "af076ca3"
    assert old_hash_of("P_2024_NDRC_718") == "718"
    assert old_hash_of("P_2024_SC_12_a") == "12_a"   # 多段:num+碰撞后缀不丢


def test_region_specific_name_placeholder_code_not_overwritten():
    # 区级名具体但 code 占位 000000 -> 不算破损,不被域名级(市)降级覆盖
    reg = {"www.shanghai.gov.cn": _entry(domain="www.shanghai.gov.cn", issuer_short="SH",
            issuer_canonical="上海市人民政府",
            region={"level": "市", "code": "310000", "name": "上海市"})}
    rec = FakeRec("P_2024_SH_41", "上海市崇明区关于充电的通知",
                  "https://www.shanghai.gov.cn/x.html", date="2024-05-01",
                  raw_fm={"region": {"level": "区", "code": "000000", "name": "上海市崇明区"}},
                  issuer=["上海市崇明区人民政府"])
    ri = resolve_identity(rec, reg, body_tail="2024年5月1日", existing_ids=set())
    assert "region" not in ri.fields


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
    # pid 已是正确 P_<year>_SD_<hash>,region/issuer/date 均已正确 -> id 不动
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2016_SD_af076ca3", "济南市人民政府办公厅关于X的通知",
                  "https://www.jinan.gov.cn/x.html",
                  date="2016-03-17",
                  raw_fm={"region": {"level": "市", "code": "370100", "name": "济南市"}},
                  issuer=["济南市人民政府办公厅"])
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


def test_valid_specific_region_not_overwritten():
    # 已有有效更精确 region(区级)-> 不被域名级(市)覆盖
    reg = {"www.beijing.gov.cn": _entry(domain="www.beijing.gov.cn", issuer_short="BJ",
            issuer_canonical="北京市人民政府",
            region={"level":"市","code":"110000","name":"北京市"})}
    rec = FakeRec("P_2024_BJ_abc12345", "北京市朝阳区关于充电设施的通知",
                  "https://www.beijing.gov.cn/x.html", date="2024-05-01",
                  raw_fm={"region":{"level":"区","code":"110105","name":"北京市朝阳区"}},
                  issuer=["北京市朝阳区人民政府"])
    ri = resolve_identity(rec, reg, body_tail="2024年5月1日", existing_ids=set())
    assert "region" not in ri.fields            # 不覆盖有效精确 region
    assert "id" not in ri.fields                # 前缀 BJ 好、date 合理 -> id 不动
    assert "issuer" not in ri.fields            # issuer 已是真机关名 -> 不动


def test_national_mirror_does_not_overwrite_valid_local_region():
    # 政策挂国家级门户镜像(域名->national),但本体是天津 -> 不可降级为全国
    reg = {"www.gov.cn": _entry(domain="www.gov.cn", issuer_short="GWY",
            issuer_canonical="国务院",
            region={"level":"国家","code":"000000","name":"全国"})}
    rec = FakeRec("P_2024_TJ_01010970", "天津市关于新能源的通知",
                  "https://www.gov.cn/x.html", date="2024-03-01",
                  raw_fm={"region":{"level":"省","code":"120000","name":"天津市"}},
                  issuer=["天津市人民政府"])
    ri = resolve_identity(rec, reg, body_tail="2024年3月1日", existing_ids=set())
    assert "region" not in ri.fields            # 有效 local 不被 national 覆盖


def test_broken_region_still_fixed():
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2015_GO_af076ca3", "济南市人民政府办公厅关于X的通知",
                  "https://www.jinan.gov.cn/x.html", date="2016-03-17",
                  raw_fm={"region":{"level":"国家","code":"000000","name":"未知"}},
                  issuer=["政府门户.www.jinan.gov.cn"])
    ri = resolve_identity(rec, reg, body_tail="2016年3月17日", existing_ids=set())
    assert ri.fields["region"].value["name"] == "济南市"   # 破损 -> 修
    assert ri.fields["issuer"].value == ["济南市人民政府办公厅"]  # 垃圾 -> 修
    assert ri.fields["id"].value == "P_2016_SD_af076ca3"   # GO -> 修


def test_valid_date_not_overwritten():
    reg = {"www.jinan.gov.cn": _entry()}
    rec = FakeRec("P_2024_SD_x", "济南市人民政府办公厅关于X的通知",
                  "https://www.jinan.gov.cn/x.html", date="2024-05-01",
                  raw_fm={"region":{"level":"市","code":"370100","name":"济南市"}},
                  issuer=["济南市人民政府办公厅"])
    ri = resolve_identity(rec, reg, body_tail="落款 2016年3月17日", existing_ids=set())
    assert "date" not in ri.fields              # 合理 date 不被落款覆盖
