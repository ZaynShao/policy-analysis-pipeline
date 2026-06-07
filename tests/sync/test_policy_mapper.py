import datetime

import pytest

from scripts.sync.policy_mapper import (
    map_business_view,
    importance_to_enum,
    parse_issue_date,
    map_policy_row,
)

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

def test_parse_issue_date():
    assert parse_issue_date("2025-05-27") == datetime.date(2025, 5, 27)
    for bad in ["", "abc", None]:
        with pytest.raises(ValueError):
            parse_issue_date(bad)

def test_map_policy_row_includes_core_and_pipeline_fields():
    core = {
        "title": "核心标题",
        "issuer": "发文机关",
        "date": "2025-05-27",
        "content": "正文",
        "doc_number": "文号",
        "source_url": "https://example.com",
        "region": "全国",
    }
    row = map_policy_row(_bv(), core, pipeline_version=1)
    assert row["title"] == "核心标题"
    assert row["issuer"] == "发文机关"
    assert row["content"] == "正文"
    assert row["source"] == "AUTO"
    assert row["issue_date"] == datetime.date(2025, 5, 27)
    assert row["pipeline_pid"] == "P_2024_NDRC_718"
    assert row["importance"] == "MAJOR"

def test_map_policy_row_rejects_bad_date():
    core = {"title": "t", "issuer": "i", "date": "", "content": "c"}
    with pytest.raises(ValueError):
        map_policy_row(_bv(), core, pipeline_version=1)

def test_map_policy_row_rejects_empty_title():
    core = {"title": "", "issuer": "i", "date": "2025-05-27", "content": "c"}
    with pytest.raises(ValueError):
        map_policy_row(_bv(), core, pipeline_version=1)

def test_map_policy_row_rejects_empty_content():
    core = {"title": "t", "issuer": "i", "date": "2025-05-27", "content": ""}
    with pytest.raises(ValueError):
        map_policy_row(_bv(), core, pipeline_version=1)
