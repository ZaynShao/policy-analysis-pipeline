from scripts.l1_review_consumer.envelope import wrap_verdict, ENVELOPE_V


def test_wrap_builds_idem_key_and_defaults():
    raw = {"ref": "swt.hebei.gov.cn", "kind": "fetch_fail", "verdict": "retry",
           "reviewer": "zayn", "note": "换 UA", "decided_run": "run42",
           "corrections": {"retry_params": {"ua": "mobile"}}}
    env = wrap_verdict(raw, decided_at="2026-06-08T10:00:00Z")
    assert env["envelope_v"] == ENVELOPE_V
    assert env["pool"] == "l1_source_quality"
    assert env["idem_key"] == "fetch_fail:swt.hebei.gov.cn:run42"
    assert env["applied"] is False and env["applied_at"] is None
    assert env["corrections"]["retry_params"]["ua"] == "mobile"


def test_wrap_rejects_bad_verdict():
    raw = {"ref": "x", "kind": "gate", "verdict": "nonsense",
           "reviewer": "z", "note": "", "decided_run": "r1"}
    try:
        wrap_verdict(raw, decided_at="2026-06-08T10:00:00Z")
        assert False, "should have raised"
    except ValueError as e:
        assert "verdict" in str(e)


def test_wrap_rejects_unknown_kind():
    raw = {"ref": "x", "kind": "bogus", "verdict": "pass",
           "reviewer": "z", "note": "", "decided_run": "r1"}
    try:
        wrap_verdict(raw, decided_at="2026-06-08T10:00:00Z")
        assert False, "should have raised"
    except ValueError as e:
        assert "kind" in str(e)
