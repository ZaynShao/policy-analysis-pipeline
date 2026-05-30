from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.id_issuer_check import parse_issuer_short, check_corpus


def _rec(pid, issuer, canon=None):
    return PolicyRecord(pid=pid, path="/x.md", title="t", official_number="",
        date="2024-01-01", issuer=[issuer], issuer_canonical=canon or [],
        url="", body_head="", raw_fm={})


def test_parse_issuer_short_handles_multiseg():
    assert parse_issuer_short("P_2024_NDRC_718") == "NDRC"
    assert parse_issuer_short("P_2025_BJ_DRC_8") == "BJ_DRC"


def test_flags_mismatch_only():
    recs = [
        _rec("P_2024_NDRC_718", "国家发展和改革委员会", ["ndrc"]),   # 一致
        _rec("P_2024_GO_7", "广州市商务局", []),                     # 错:GO=国务院
    ]
    findings = check_corpus(recs)
    assert len(findings) == 1
    assert findings[0].pid == "P_2024_GO_7"
    assert findings[0].check == "id_issuer"
