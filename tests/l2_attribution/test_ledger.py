from scripts.l2_attribution.ledger import load_ledger, issuer_short_of_id, cross_check


def test_issuer_short_of_id():
    assert issuer_short_of_id("P_2016_SD_af076ca3") == "SD"
    assert issuer_short_of_id("P_2016_SD_af076ca3_a") == "SD"


def test_cross_check_agree():
    led = {"suggested_issuer_short": "SD", "true_region": "济南市"}
    status, _ = cross_check("P_2016_SD_af076ca3", led)
    assert status == "agree"


def test_cross_check_disagree():
    led = {"suggested_issuer_short": "NDRC", "true_region": "national"}
    status, detail = cross_check("P_2016_SD_af076ca3", led)
    assert status == "disagree"
    assert detail["resolver"] == "SD" and detail["ledger"] == "NDRC"


def test_load_ledger_indexes_by_pid(tmp_path):
    p = tmp_path / "led.jsonl"
    p.write_text('{"pid":"P_x","suggested_issuer_short":"SD","true_region":"济南市"}\n',
                 encoding="utf-8")
    led = load_ledger(str(p))
    assert led["P_x"]["suggested_issuer_short"] == "SD"
