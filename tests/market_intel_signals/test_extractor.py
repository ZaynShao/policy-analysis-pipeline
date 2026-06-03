from scripts.market_intel_signals.extractor import (
    build_policy_index,
    classify_signal_type,
    extract_market_signal,
    locate_policy_by_id_or_alias,
    parse_policy_file,
)


def test_locate_policy_by_alias(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    path = root / "policy.md"
    path.write_text(
        "---\n"
        "id: P_NEW\n"
        "aliases: [P_OLD]\n"
        "title: old alias\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )

    found = locate_policy_by_id_or_alias(root, "P_OLD")

    assert found == path


def test_build_policy_index_maps_ids_and_aliases(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    path = root / "policy.md"
    path.write_text(
        "---\n"
        "id: P_NEW\n"
        "aliases: [P_OLD]\n"
        "title: old alias\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )

    index = build_policy_index(root)

    assert index["P_NEW"] == path
    assert index["P_OLD"] == path


def test_classify_signal_type_project_list():
    assert classify_signal_type("银川电网侧储能项目清单公示", "") == "project_list"


def test_classify_signal_type_capacity_and_price():
    assert classify_signal_type("杭州2026Q1分布式光伏可开放容量表", "") == "capacity_disclosure"
    assert classify_signal_type("浙江省成品油价格调整", "") == "price_signal"


def test_classify_signal_type_prefers_title_over_body():
    assert classify_signal_type("银川电网侧储能项目清单公示(2.4GW/8.1GWh)", "公开遴选") == "project_list"
    assert classify_signal_type("南方电网首个交流V2G落地海口(项目动态)", "招标") == "pilot_landing"
    assert classify_signal_type("杭州储能改造入选国家发改委典型案例", "补贴") == "project_case"
    assert classify_signal_type("成都高新区虚拟电厂建设项目（一期）（第二次）设计-采购", "交易") == "tender_procurement"


def test_parse_policy_file_handles_title_containing_dashes(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    path = root / "policy.md"
    path.write_text(
        "---\n"
        "id: P_NEW\n"
        "title: 9个城市和30个项目列入首批车网互动规模化应用试点---国家能源局\n"
        "date: '2025-04-25'\n"
        "region: {level: 国家, code: '000000', name: 全国}\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )

    doc = parse_policy_file(path, root)

    assert doc.frontmatter["date"] == "2025-04-25"
    assert doc.frontmatter["region"]["name"] == "全国"
    assert doc.body == "正文"


def test_extract_signal_uses_theme_region_and_business_lines(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    path = root / "policy.md"
    path.write_text(
        "---\n"
        "id: P_NEW\n"
        "aliases: [P_OLD]\n"
        "title: 南方电网首个交流V2G落地海口\n"
        "date: '2025-12-27'\n"
        "region: {level: 市, code: '460100', name: 海口市}\n"
        "provenance: {url: 'https://example.com'}\n"
        "---\n"
        "车网互动项目正式投运。",
        encoding="utf-8",
    )
    doc = parse_policy_file(path, root)

    signal = extract_market_signal({"pid": "P_OLD"}, doc, {"v2g": ["V2G", "车网互动"]})

    assert signal.source_pid == "P_OLD"
    assert signal.current_policy_id == "P_NEW"
    assert signal.theme_ids == ["v2g"]
    assert signal.business_lines == ["charging", "power"]
    assert signal.signal_type == "pilot_landing"
    assert signal.time_validity == "point_in_time"
    assert signal.region == {"level": "市", "code": "460100", "name": "海口市"}
    assert signal.source_url == "https://example.com"
