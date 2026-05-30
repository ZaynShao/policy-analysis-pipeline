from scripts.l1_audit.corpus import load_policies


def test_load_parses_frontmatter_and_normalizes_issuer(vault_policies):
    recs = load_policies(str(vault_policies))
    assert len(recs) == 1
    r = recs[0]
    assert r.pid == "P_2025_NDRC_357_a"
    assert r.issuer == ["国家发展和改革委员会"]      # 单值包成 list
    assert r.issuer_canonical == ["ndrc"]
    assert r.url == "https://www.ndrc.gov.cn/a/2025-03-01/x.html"
    assert r.date == "2025-03-01"
    assert r.body_head.startswith("## 政策原文")
