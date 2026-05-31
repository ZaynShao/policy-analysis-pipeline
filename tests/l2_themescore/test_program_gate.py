from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.program_gate import check_draft

VALID_IDS = ["power_market","vpp_theme","energy_storage_theme"]
KEYS = {"加油","充电","电力_储能_V2G_交易"}

def _draft(**kw):
    base = dict(pid="P", themes=["power_market"], primary_theme="power_market",
                scores=Scores(5,4,4,4,4,5), importance=4, action_class="A",
                value_tags=["机会"], gate_passed_deep=True,
                影响分析={k:"x" for k in KEYS}, 行动建议=["A 趁早:做"])
    base.update(kw); return BusinessViewDraft(**base)

def test_clean_passes():
    assert check_draft(_draft(), VALID_IDS) == []

def test_primary_not_in_themes():
    v = check_draft(_draft(primary_theme="vpp_theme"), VALID_IDS)
    assert any("primary" in x for x in v)

def test_theme_not_in_registry():
    v = check_draft(_draft(themes=["bogus"], primary_theme="bogus"), VALID_IDS)
    assert any("registry" in x for x in v)

def test_impact_keys_wrong():
    v = check_draft(_draft(影响分析={"加油":"x","乡村":"y"}), VALID_IDS)
    assert any("影响分析键" in x for x in v)

def test_deep_iff_gate_violation():
    v = check_draft(_draft(gate_passed_deep=True, 影响分析=None, 行动建议=[]), VALID_IDS)
    assert any("深档" in x for x in v)

def test_formula_mismatch():
    v = check_draft(_draft(importance=1), VALID_IDS)
    assert any("公式" in x for x in v)
