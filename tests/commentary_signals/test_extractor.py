from pathlib import Path

from scripts.commentary_signals.extractor import (
    commentary_id,
    extract_commentary_signal,
    parse_markdown,
)


def test_parse_markdown_reads_frontmatter_and_body(tmp_path):
    path = tmp_path / "评论.md"
    path.write_text(
        "---\n"
        "title: 电价改革解读\n"
        "related_policy:\n"
        "  - P_2025_NDRC_136\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )

    doc = parse_markdown(path, tmp_path)

    assert doc.frontmatter["title"] == "电价改革解读"
    assert doc.body == "正文"
    assert doc.relative_path == "评论.md"


def test_commentary_id_is_path_stable(tmp_path):
    path = tmp_path / "a.md"

    assert commentary_id(path, tmp_path) == commentary_id(path, tmp_path)
    assert commentary_id(path, tmp_path).startswith("C_")


def test_extract_commentary_signal_for_linked_commentary(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(
        "---\n"
        "title: 136号文短期风险\n"
        "related_policy:\n"
        "  - P_2025_NDRC_136\n"
        "business_tag: power\n"
        "---\n"
        "短期收益不确定性上升,但长期市场化机会明确。",
        encoding="utf-8",
    )
    doc = parse_markdown(path, tmp_path)

    signal = extract_commentary_signal(doc, {"power_market": ["电力市场", "电价", "市场化"]})

    assert signal is not None
    assert signal.related_policy_ids == ["P_2025_NDRC_136"]
    assert signal.signal_role == "risk"
    assert signal.theme_ids == ["power_market"]
    assert signal.confidence == 0.72
    assert "不确定性" in signal.evidence


def test_extract_commentary_signal_normalizes_string_related_policy(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(
        "---\n"
        "title: V2G落地机会\n"
        "related_policy: P_2024_NDRC_718\n"
        "---\n"
        "车网互动试点项目推进,充放电商业模式机会明确。",
        encoding="utf-8",
    )
    doc = parse_markdown(path, tmp_path)

    signal = extract_commentary_signal(doc, {"v2g": ["V2G", "车网互动", "充放电"]})

    assert signal is not None
    assert signal.related_policy_ids == ["P_2024_NDRC_718"]
    assert signal.signal_role == "opportunity"
    assert signal.theme_ids == ["v2g"]


def test_unreadable_pdf_body_uses_title_only_and_sanitized_evidence(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(
        "---\n"
        "title: V2G政策解读\n"
        "related_policy: P_2024_NDRC_718\n"
        "---\n"
        "%PDF-1.7 \x00\x01\x02 乱码正文 V2G",
        encoding="utf-8",
    )
    doc = parse_markdown(path, tmp_path)

    signal = extract_commentary_signal(doc, {"v2g": ["V2G", "车网互动", "充放电"]})

    assert signal is not None
    assert signal.theme_ids == ["v2g"]
    assert "正文不可读" in signal.evidence
    assert "\x00" not in signal.evidence
    assert "\x01" not in signal.evidence


def test_unlinked_commentary_returns_no_signal(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\ntitle: 行业新闻\n---\n正文", encoding="utf-8")
    doc = parse_markdown(path, tmp_path)

    assert extract_commentary_signal(doc, {}) is None


def test_not_policy_related_returns_no_signal(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(
        "---\n"
        "title: 海外行情\n"
        "related_policy: [P_2025_X]\n"
        "not_policy_related: true\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )
    doc = parse_markdown(path, tmp_path)

    assert extract_commentary_signal(doc, {}) is None
