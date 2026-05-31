from scripts.l2_attribution.models import (
    ChannelEntry, ResolvedField, ResolvedIdentity, QueueRecord,
)


def test_channel_entry_region_is_nested():
    e = ChannelEntry(
        domain="www.jinan.gov.cn", issuer_short="SD",
        issuer_canonical="济南市人民政府",
        region={"level": "市", "code": "370100", "name": "济南市"},
    )
    assert e.region["level"] == "市"
    assert e.issuer_short == "SD"


def test_resolved_identity_collects_fields_and_conflicts():
    ri = ResolvedIdentity(pid="P_2015_GO_x")
    ri.set_field("region", {"level": "市", "code": "370100", "name": "济南市"},
                 method="domain_lookup", confidence=0.99, from_val="国家/000000/未知")
    ri.add_conflict("date", reason="落款抽不到且现值坏 2027",
                    signals={"frontmatter": "2027-01-01", "luokuan": None})
    assert "region" in ri.fields
    assert ri.fields["region"].method == "domain_lookup"
    assert ri.has_conflicts() is True
    assert ri.conflicts[0].field == "date"


def test_queue_record_to_dict_roundtrips():
    q = QueueRecord(pid="P_x", field="issuer", reason="转载:标题机关与域名不符",
                    signals={"title_issuer": "国务院办公厅", "domain_region": "承德市"})
    d = q.to_dict()
    assert d["pid"] == "P_x" and d["field"] == "issuer"
    assert d["signals"]["domain_region"] == "承德市"
