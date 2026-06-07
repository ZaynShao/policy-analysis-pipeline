import datetime


def test_zero_alert_for_key_province_theme():
    from scripts.l1_collect.audit_coverage import get_zero_alerts
    m = {"江苏省": {"充电": 0, "加油": 3, "电力": 5}}
    a = get_zero_alerts(m)
    assert any(x["province"] == "江苏省" and x["theme"] == "充电" for x in a)


def test_no_zero_alert_when_covered():
    from scripts.l1_collect.audit_coverage import get_zero_alerts
    assert get_zero_alerts({"广东省": {"充电": 12, "加油": 8, "电力": 15}}) == []


def test_freshness_flags_stale():
    from scripts.l1_collect.audit_coverage import check_freshness
    old = (datetime.date.today() - datetime.timedelta(days=70)).isoformat()
    new = datetime.date.today().isoformat()
    a = check_freshness({"吉林省": old, "广东省": new}, stale_days=60)
    assert any(x["province"] == "吉林省" for x in a)
    assert all(x["province"] != "广东省" for x in a)


def test_gap_diagnosis_collection_vs_attribution():
    from scripts.l1_collect.audit_coverage import diagnose_gap
    # 该省该渠道扫描数=0 → 采集缺口
    assert diagnose_gap("江苏省", "充电", scanned_count=0)["cause"] == "collection_gap"
    # 扫到了但矩阵为0 → 归属错标
    assert diagnose_gap("江苏省", "充电", scanned_count=40)["cause"] == "attribution_gap"


def test_html_report_marks_zero():
    from scripts.l1_collect.audit_coverage import render_html_report
    html = render_html_report({"江苏省": {"充电": 0, "加油": 3, "电力": 7}},
                              alerts=[], freshness={})
    assert "<table" in html and "江苏" in html
    assert 'class="zero"' in html
