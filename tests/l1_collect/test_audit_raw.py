def test_themes_include_platform_regulation():
    from scripts._oneshot.audit_coverage_raw import THEMES
    assert "平台监管" in THEMES
    for kw in ("平台经济", "反垄断", "市场监管"):
        assert kw in THEMES["平台监管"]
