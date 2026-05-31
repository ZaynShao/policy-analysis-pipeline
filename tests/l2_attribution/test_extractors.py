from scripts.l2_attribution.extractors import (
    extract_issuer_from_title, extract_luokuan_date,
)


def test_issuer_from_simple_title():
    t = "济南市人民政府办公厅关于进一步加强成品油监管工作的通知"
    assert extract_issuer_from_title(t) == "济南市人民政府办公厅"


def test_issuer_from_joint_title():
    t = "国家发展改革委 国家能源局关于印发电力体制改革配套文件的通知"
    assert extract_issuer_from_title(t) == "国家发展改革委 国家能源局"


def test_issuer_title_no_match_returns_none():
    assert extract_issuer_from_title("电力现货市场基本规则(试行)") is None


def test_luokuan_date_chinese():
    body_tail = "……结合我市实际,现通知如下。\n\n济南市人民政府办公厅\n\n2016年3月17日\n\n附件:部门工作任务分工"
    assert extract_luokuan_date(body_tail) == "2016-03-17"


def test_luokuan_date_b4_case():
    body_tail = "……自本规则印发之日起施行。\n\n国家发展改革委\n国家能源局\n2023年9月15日"
    assert extract_luokuan_date(body_tail) == "2023-09-15"


def test_luokuan_date_none_when_absent():
    assert extract_luokuan_date("没有任何日期的正文结尾。") is None
