from scripts.sync.relation_mapper import map_relation, VALID_RELATION_TYPES

def test_valid_types_count():
    assert len(VALID_RELATION_TYPES) == 9
    assert "derives_from" in VALID_RELATION_TYPES
    assert "conflicts_with" in VALID_RELATION_TYPES

def test_map_basic():
    rec = {
        "from_pid": "P_2024_NDRC_718",
        "to_pid": "P_2023_NDRC_100",
        "relation_type": "derives_from",
        "confidence": 0.9,
        "evidence": "为贯彻落实……",
    }
    row = map_relation(rec, pipeline_version=1)
    assert row["from_pid"] == "P_2024_NDRC_718"
    assert row["to_pid"] == "P_2023_NDRC_100"
    assert row["relation_type"] == "derives_from"
    assert row["confidence"] == 0.9
    assert row["pipeline_version"] == 1

def test_map_rejects_unknown_type():
    rec = {"from_pid": "P_A", "to_pid": "P_B", "relation_type": "bogus"}
    try:
        map_relation(rec, pipeline_version=1)
        assert False, "should raise"
    except ValueError:
        pass

def test_map_missing_confidence_ok():
    rec = {"from_pid": "P_A", "to_pid": "P_B", "relation_type": "references"}
    row = map_relation(rec, pipeline_version=1)
    assert row["confidence"] is None
