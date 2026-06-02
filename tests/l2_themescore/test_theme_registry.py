from scripts.l2_themescore.theme_registry import ThemeRegistry, canonical_theme_id, canonicalize_theme_ids

REG = """
schema_version: 1.0
themes:
  - {id: vpp_theme, zh: 虚拟电厂, aliases: [虚拟电厂, 负荷聚合, 可调节负荷]}
  - {id: aggregator_access, zh: 聚合商准入, aliases: [聚合商, 负荷聚合]}
  - {id: power_market, zh: 电力市场, aliases: [电力市场, 现货交易]}
"""

def test_load_ids(tmp_path):
    p = tmp_path/"r.yaml"; p.write_text(REG, encoding="utf-8")
    r = ThemeRegistry.load(str(p))
    assert set(r.ids) == {"vpp_theme","aggregator_access","power_market"}

def test_alias_can_map_multiple_themes(tmp_path):
    p = tmp_path/"r.yaml"; p.write_text(REG, encoding="utf-8")
    r = ThemeRegistry.load(str(p))
    assert set(r.alias_index["负荷聚合"]) == {"vpp_theme","aggregator_access"}
    assert r.alias_index["现货交易"] == ["power_market"]

def test_validate(tmp_path):
    p = tmp_path/"r.yaml"; p.write_text(REG, encoding="utf-8")
    r = ThemeRegistry.load(str(p))
    assert r.is_valid("vpp_theme") and not r.is_valid("nonsense_theme")

def test_canonical_theme_id_handles_none_and_suffix_alias():
    assert canonical_theme_id(None, ["v2g"]) == ""
    assert canonical_theme_id("v2g_theme", ["v2g"]) == "v2g"
    assert canonicalize_theme_ids([None, "", "v2g_theme", "v2g"], ["v2g"]) == ["v2g"]
