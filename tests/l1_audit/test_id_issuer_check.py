from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.id_issuer_check import parse_issuer_short, check_corpus, check_one

def _rec(pid, issuer, canon=None):
    return PolicyRecord(pid=pid, path="/x.md", title="t", official_number="",
        date="2024-01-01", issuer=[issuer] if issuer else [], issuer_canonical=canon or [],
        url="", body_head="", raw_fm={})

def test_parse_issuer_short_multiseg_and_collision_suffix():
    assert parse_issuer_short("P_2024_NDRC_718") == "NDRC"
    assert parse_issuer_short("P_2025_BJ_DRC_8") == "BJ_DRC"
    assert parse_issuer_short("P_2025_NDRC_357_a") == "NDRC"   # 碰撞后缀剥离
    assert parse_issuer_short("P_2024_MOFCOM_75_b") == "MOFCOM"

def test_canonical_consistent_not_flagged():
    assert check_one(_rec("P_2024_NDRC_718", "国家发展改革委", ["ndrc"])) is None

def test_canonical_mismatch_flagged_high_confidence():
    f = check_one(_rec("P_2024_GO_7", "某文", ["ndrc"]))   # id 说 GO,canonical 说 ndrc
    assert f is not None and f.detail["source"] == "canonical"
    assert f.detail["expected_short"] == "NDRC"

def test_keyword_fallback_tolerates_abbreviation():
    # 无 canonical,issuer 用缩写"国家发展改革委"(无"和") → 仍应一致,不 flag
    assert check_one(_rec("P_2024_NDRC_718", "国家发展改革委", [])) is None

def test_keyword_fallback_flags_real_mismatch_low_confidence():
    f = check_one(_rec("P_2024_GO_7", "广州市商务局", []))
    assert f is not None and f.detail["source"] == "keyword"

def test_check_corpus_collects():
    recs = [_rec("P_2024_NDRC_1", "国家发展改革委", ["ndrc"]),    # ok
            _rec("P_2024_GO_7", "广州市商务局", [])]              # flag(keyword)
    assert len(check_corpus(recs)) == 1
