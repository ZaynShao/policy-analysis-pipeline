from scripts.sync.policy_mapper import map_business_view, importance_to_enum

def _bv():
    return {
        "pid": "P_2024_NDRC_718",
        "themes": ["power_market", "energy_storage_theme"],
        "primary_theme": "power_market",
        "重要性": 4,
        "scores": {"D1": 5, "D2": 4, "D3": 4, "D4": 4, "D5": 4, "D6": 5},
        "value_tags": ["机会"],
        "影响分析": {"加油": "a", "充电": "b", "电力_储能_V2G_交易": "c"},
        "comprehensive": True,
    }

def test_importance_to_enum_mapping():
    assert importance_to_enum(5) == "STRATEGIC"
    assert importance_to_enum(4) == "MAJOR"
    assert importance_to_enum(3) == "GENERAL"
    assert importance_to_enum(2) == "INFO"
    assert importance_to_enum(1) == "INFO"

def test_map_basic_fields():
    row = map_business_view(_bv(), pipeline_version=1)
    assert row["pipeline_pid"] == "P_2024_NDRC_718"
    assert row["importance"] == "MAJOR"
    assert row["pipeline_version"] == 1

def test_map_themes_is_json_serializable():
    import json
    row = map_business_view(_bv(), pipeline_version=1)
    themes = json.loads(row["pipeline_themes"])
    assert themes[0]["id"] == "power_market"
    assert themes[0]["isPrimary"] is True
    assert themes[1]["isPrimary"] is False

def test_map_scores_and_impact():
    import json
    row = map_business_view(_bv(), pipeline_version=1)
    assert json.loads(row["pipeline_scores"])["D1"] == 5
    assert "充电" in row["pipeline_impact"]

def test_map_comprehensive_flag_in_themes_meta():
    import json
    row = map_business_view(_bv(), pipeline_version=1)
    themes = json.loads(row["pipeline_themes"])
    assert any(t.get("isComprehensive") for t in themes) or row.get("comprehensive") is True
