from scripts.l1_audit.models import PolicyRecord
from scripts.l1_audit.scans import scan_p1900


def _rec(pid):
    return PolicyRecord(
        pid=pid,
        path=f"/{pid}.md",
        title="t",
        official_number="",
        date="",
        issuer=[],
        issuer_canonical=[],
        url="",
        body_head="",
        raw_fm={}
    )


def test_flags_p1900_only():
    recs = [_rec("P_1900_SX_caf8e7eb"), _rec("P_2025_NDRC_1")]
    findings = scan_p1900(recs)
    assert len(findings) == 1
    assert findings[0].pid == "P_1900_SX_caf8e7eb"
    assert findings[0].check == "p1900"
