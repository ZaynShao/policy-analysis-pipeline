from pathlib import Path
from scripts.analysis_semantic_relations.loaders import (
    PolicyView, load_policy_views, load_hpr_basis_pairs, _year_of, _norm_issuer,
)


def test_year_parsing():
    assert _year_of("2023-05-01") == 2023
    assert _year_of("2023年5月") == 2023
    assert _year_of("") is None


def test_policy_view_from_fixture(tmp_path):
    # business_view fixture
    bv = tmp_path / "_meta" / "business_view"; bv.mkdir(parents=True)
    (bv / "P_X.yaml").write_text(
        "pid: P_X\nthemes: [power_market]\nprimary_theme: power_market\n重要性: 4\n",
        encoding="utf-8")
    views = load_policy_views(
        policies=[PolicyView(pid="P_X", title="某电力市场方案", region_level="省",
                             region_name="广东", issuer="广东省发改委", year=2023,
                             themes=[], primary_theme="", importance=None)],
        vault=tmp_path)
    v = views["P_X"]
    assert v.themes == ["power_market"] and v.primary_theme == "power_market" and v.importance == 4


def test_hpr_basis_pairs(tmp_path):
    p = tmp_path / "hpr.jsonl"
    p.write_text('{"from":"P_LOCAL","to":"P_NAT","rel":"cites_basis"}\n'
                 '{"from":"P_A","to":"P_B","rel":"references"}\n', encoding="utf-8")
    pairs = load_hpr_basis_pairs(p)
    assert ("P_LOCAL", "P_NAT") in pairs  # cites_basis 计入 basis
    assert ("P_A", "P_B") in pairs        # references 也计入(弱 basis 信号)


def test_norm_issuer():
    # None -> ""
    assert _norm_issuer(None) == ""
    # list -> joined non-empty string (not the Python list repr)
    result = _norm_issuer(["广东省发改委", "广东省能源局"])
    assert result != ""
    assert "None" not in result
    assert "[" not in result  # must not be str([...])
    assert "广东省发改委" in result
    # scalar -> str().strip()
    assert _norm_issuer("国家发改委") == "国家发改委"
    # empty string -> ""
    assert _norm_issuer("") == ""
    # empty list -> ""
    assert _norm_issuer([]) == ""
    # None-issuer must be falsy (empty string)
    assert not _norm_issuer(None)
