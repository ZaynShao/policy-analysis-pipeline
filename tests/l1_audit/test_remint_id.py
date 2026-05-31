"""remint_id 原语:就地重算 id/issuer/region + aliases 保旧 id,文件名不变,body 保留。"""
import yaml
from pathlib import Path
from scripts.l1_audit.apply import remint_id, _FM_RE


def _write(policies: Path, fname, pid, issuer="国务院办公厅", date="2024-01-01"):
    fm = (f"---\nid: {pid}\ntitle: 某政策标题\nofficial_number: 发改〔2024〕1号\n"
          f"date: '{date}'\nissuer: {issuer}\nissuer_canonical: [go]\n"
          f"source_url: https://x.gov.cn/a.html\n---\n\n## 政策原文\n正文内容保留。\n")
    p = policies / fname
    p.write_text(fm, encoding="utf-8")
    return p


def _read_fm_body(path):
    text = Path(path).read_text(encoding="utf-8")
    m = _FM_RE.search(text)
    return yaml.safe_load(m.group(1)), m.group(2)


def test_remint_edits_in_place_keeps_filename(tmp_path):
    policies = tmp_path / "0_raw" / "policies"
    policies.mkdir(parents=True)
    src = _write(policies, "某政策标题.md", "P_2024_GO_a8363ed7")

    dst = remint_id(str(policies), "P_2024_GO_a8363ed7",
                    new_id="P_2024_GD_a8363ed7",
                    true_issuer="广州市人民政府", true_region="广州市",
                    fixed_at="2026-05-31")

    # 文件名不变、原位
    assert Path(dst) == src
    assert src.exists()
    assert sorted(p.name for p in policies.glob("*.md")) == ["某政策标题.md"]

    fm, body = _read_fm_body(src)
    assert fm["id"] == "P_2024_GD_a8363ed7"
    assert "P_2024_GO_a8363ed7" in fm["aliases"]
    assert fm["issuer"] == ["广州市人民政府"]
    assert fm["region"] == "广州市"
    # 审计字段
    assert fm["id_fixed_from"] == "P_2024_GO_a8363ed7"
    assert fm["id_fixed_method"] == "phase2_2b_llm_classify"
    assert fm["id_fixed_at"] == "2026-05-31"
    # issuer_canonical 不动
    assert fm["issuer_canonical"] == ["go"]
    # body 保留
    assert "正文内容保留。" in body


def test_remint_date_fix_path(tmp_path):
    policies = tmp_path / "0_raw" / "policies"
    policies.mkdir(parents=True)
    _write(policies, "x.md", "P_2027_GO_572b0ea8", date="2027-01-01")

    remint_id(str(policies), "P_2027_GO_572b0ea8",
              new_id="P_2023_NDRC_572b0ea8",
              true_issuer="国家发展改革委、国家能源局", true_region="national",
              date_fix="2023-09", fixed_at="2026-05-31")

    fm, _ = _read_fm_body(policies / "x.md")
    assert fm["date"] == "2023-09"
    assert fm["date_fixed_from"] == "2027-01-01"


def test_remint_no_double_append_alias(tmp_path):
    policies = tmp_path / "0_raw" / "policies"
    policies.mkdir(parents=True)
    _write(policies, "y.md", "P_2024_GO_a8363ed7")

    remint_id(str(policies), "P_2024_GO_a8363ed7", new_id="P_2024_GD_a8363ed7",
              true_issuer="广州市人民政府", true_region="广州市", fixed_at="2026-05-31")
    # 第二次按 new_id 再 remint,旧 id 已在 aliases,不应重复
    remint_id(str(policies), "P_2024_GD_a8363ed7", new_id="P_2024_GD_a8363ed7",
              true_issuer="广州市人民政府", true_region="广州市", fixed_at="2026-05-31")

    fm, _ = _read_fm_body(policies / "y.md")
    assert fm["aliases"].count("P_2024_GO_a8363ed7") == 1
    assert fm["aliases"].count("P_2024_GD_a8363ed7") <= 1
