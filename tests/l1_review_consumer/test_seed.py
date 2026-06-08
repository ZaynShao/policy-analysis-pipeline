from scripts.l1_review_consumer.seed_fixtures import (
    fetch_fail_row, checkpoint_row, parse_ferr_filename,
)


def test_fetch_fail_row_shape():
    row = fetch_fail_row(channel="河北省商务厅", domain="swt.hebei.gov.cn",
                         url="http://swt.hebei.gov.cn/yjhxgzfa/2026/2/1.html",
                         reason="fetch_failed")
    assert row["kind"] == "fetch_fail"
    assert row["ref"] == "http://swt.hebei.gov.cn/yjhxgzfa/2026/2/1.html"
    assert row["suggested_action"] in ("retry", "unfetchable", "drop")
    assert row["channel"] == "河北省商务厅"
    assert "swt.hebei" in row["evidence"]
    assert row["run_label"] == "seed_fixture"


def test_checkpoint_row_shape():
    row = checkpoint_row(domain="example.gov.cn", city="某市",
                         list_url="http://example.gov.cn/list")
    assert row["kind"] == "checkpoint"
    assert row["ref"] == "example.gov.cn"
    assert row["suggested_action"] == "promote"
    assert row["channel"] == "某市"


def test_parse_ferr_filename():
    ch, domain = parse_ferr_filename(
        "国家发展和改革委员会__发改委__ndrc.gov.cn__ferr.txt")
    assert ch == "国家发展和改革委员会"
    assert domain == "ndrc.gov.cn"
