from scripts.audit.principle_guard import find_policy_id_literals


def test_principle_guard_flags_hardcoded_policy_ids(tmp_path):
    target = tmp_path / "bad.py"
    target.write_text('if pid == "P_2024_GD_1234abcd":\n    pass\n', encoding="utf-8")

    findings = find_policy_id_literals([target])

    assert len(findings) == 1
    assert findings[0]["policy_id"] == "P_2024_GD_1234abcd"
    assert findings[0]["line"] == 1


def test_principle_guard_ignores_non_policy_tokens(tmp_path):
    target = tmp_path / "clean.py"
    target.write_text('pid = "P_OK"\nexample = "P_2024"\n', encoding="utf-8")

    assert find_policy_id_literals([target]) == []


def test_l2_themescore_source_has_no_policy_id_patches():
    assert find_policy_id_literals(["scripts/l2_themescore"]) == []
