import yaml
from pathlib import Path
from scripts.l2_themescore.models import Scores, BusinessViewDraft
from scripts.l2_themescore.business_view_writer import write_business_view

def _d():
    return BusinessViewDraft(pid="P_2024_NDRC_718", themes=["power_market","energy_storage_theme"],
        primary_theme="power_market", scores=Scores(5,4,4,4,4,5), importance=4, action_class="A",
        value_tags=["机会"], gate_passed_deep=True, comprehensive=True,
        影响分析={"加油":"a","充电":"b","电力_储能_V2G_交易":"c"}, 行动建议=["A 趁早:x"],
        didi_impact_one_liner="y")

def test_write_and_reload(tmp_path):
    vault = tmp_path; raw_file = "0_raw/policies/foo.md"
    out = write_business_view(_d(), str(vault), sanitized_from=raw_file, extracted_at="2026-06-01",
                              extracted_model="model-A")
    assert Path(out).exists()
    data = yaml.safe_load(Path(out).read_text(encoding="utf-8"))
    assert data["pid"] == "P_2024_NDRC_718"
    assert data["themes"] == ["power_market","energy_storage_theme"]
    assert data["primary_theme"] == "power_market"
    assert data["重要性"] == 4
    assert set(data["影响分析"].keys()) == {"加油","充电","电力_储能_V2G_交易"}
    assert data["sanitized_from"] == raw_file
    assert data["gate_passed_deep"] is True
    assert data["comprehensive"] is True

def test_overwrites_整文件重生(tmp_path):
    vault = tmp_path
    write_business_view(_d(), str(vault), sanitized_from="x", extracted_at="d", extracted_model="m")
    d2 = _d(); d2.themes = ["power_market"]; d2.primary_theme="power_market"
    out = write_business_view(d2, str(vault), sanitized_from="x", extracted_at="d", extracted_model="m")
    data = yaml.safe_load(Path(out).read_text(encoding="utf-8"))
    assert data["themes"] == ["power_market"]

def test_never_writes_raw(tmp_path):
    vault = tmp_path; (vault/"0_raw"/"policies").mkdir(parents=True)
    raw = vault/"0_raw"/"policies"/"foo.md"; raw.write_text("ORIG", encoding="utf-8")
    write_business_view(_d(), str(vault), sanitized_from="0_raw/policies/foo.md",
                        extracted_at="d", extracted_model="m")
    assert raw.read_text(encoding="utf-8") == "ORIG"
