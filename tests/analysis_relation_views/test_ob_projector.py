"""OB 双链投影器测试 — _rev_ 前缀 / 显式链接 / body 锚点 / 图谱孤岛 / 幂等 / 命名表。"""
from __future__ import annotations

from pathlib import Path

from scripts.analysis_relation_views.merge import merge_edges
from scripts.analysis_relation_views.models import RelEdge
from scripts.analysis_relation_views.ob_projector import project_pages


def _project(edges, raw_index, tmp_path) -> Path:
    out = tmp_path / "_index_by_policy"
    project_pages(edges, raw_index, out)
    return out


def test_filenames_have_rev_prefix(sem_jsonl, hpr_jsonl, raw_index, tmp_path):
    """文件名必须 _rev_<pid>.md,绝不裸 {pid}.md(SCHEMA §5.3 硬约束)。"""
    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    out = _project(res.edges, raw_index, tmp_path)
    files = sorted(p.name for p in out.glob("*.md"))
    assert files, "应生成至少一页"
    for name in files:
        assert name.startswith("_rev_"), f"{name} 缺 _rev_ 前缀"
    # 绝无裸 {pid}.md(会截胡 [[P_xxx]] 使 raw 政策图谱孤岛)
    assert not (out / "P_2026_MIIT_13.md").exists()
    assert (out / "_rev_P_2026_MIIT_13.md").exists()


def test_p_2026_miit_13_not_graph_isolated(sem_jsonl, hpr_jsonl, raw_index, tiny_vault, tmp_path):
    """图谱孤岛验收:R(P_2026_MIIT_13)被 A 通过 derives_from 指向 →
    R 的 _rev_R.md 存在、body 顶有 [[<R的stem>|...]] 锚点、
    且 A 的出向段有 [[<R的stem>|R_pid]]。R 不因 alias 不可靠而孤立。"""
    _, stems = tiny_vault
    r_pid = "P_2026_MIIT_13"
    a_pid = "P_2026_GD_aaaa"
    r_stem = stems[r_pid]

    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    out = _project(res.edges, raw_index, tmp_path)

    # ① R 的反链页存在
    r_page = out / f"_rev_{r_pid}.md"
    assert r_page.exists()
    r_text = r_page.read_text(encoding="utf-8")

    # ② R 的 body 顶部有图谱边锚点(显式 file_stem,alias 在 graph view 不建边)
    assert f"[[{r_stem}|" in r_text
    # 锚点出现在 frontmatter 之后、section 之前
    body = r_text.split("---", 2)[2]
    anchor_idx = body.index(f"[[{r_stem}|")
    inbound_idx = body.find("# 入向反链")
    assert anchor_idx < inbound_idx, "锚点必须在入向 section 之前(body 顶部)"

    # ③ A 的出向段有指向 R 的显式 [[<R的stem>|R_pid]]
    a_page = out / f"_rev_{a_pid}.md"
    assert a_page.exists()
    a_text = a_page.read_text(encoding="utf-8")
    assert f"[[{r_stem}|{r_pid}]]" in a_text
    assert "# 出向引用" in a_text
    assert "派生自" in a_text  # derives_from 的出向标签


def test_links_are_explicit_stem_pipe_pid(sem_jsonl, hpr_jsonl, raw_index, tiny_vault, tmp_path):
    """所有 peer 链接是显式 [[stem|pid]],不是裸 [[pid]]。"""
    _, stems = tiny_vault
    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    out = _project(res.edges, raw_index, tmp_path)
    for page in out.glob("_rev_*.md"):
        text = page.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("- [["):
                # 链接行必须含 | 分隔(显式 stem|pid),且左边是某个真实 stem
                assert "|" in line, f"裸链接(无 stem): {line}"
                inner = line.split("[[", 1)[1].split("]]", 1)[0]
                stem_part, pid_part = inner.split("|", 1)
                assert stem_part in stems.values(), f"stem 非真实 raw 文件名: {stem_part}"


def test_dangling_pid_in_no_page(sem_jsonl, hpr_jsonl, raw_index, tmp_path):
    """dangling 端点不出现在任何反链页(文件名 + 内容)。"""
    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    out = _project(res.edges, raw_index, tmp_path)
    assert not (out / "_rev_P_9999_GONE_zzzz.md").exists()
    assert not (out / "_rev_P_0000_GHOST_yyyy.md").exists()
    for page in out.glob("_rev_*.md"):
        text = page.read_text(encoding="utf-8")
        assert "P_9999_GONE_zzzz" not in text
        assert "P_0000_GHOST_yyyy" not in text


def test_idempotent_byte_identical(sem_jsonl, hpr_jsonl, raw_index, tmp_path, monkeypatch):
    """连跑两次,_rev_*.md 字节一致(钉死 last_updated 时间戳后)。"""
    import scripts.analysis_relation_views.ob_projector as ob

    monkeypatch.setattr(ob, "_now_iso", lambda: "2026-06-06T00:00:00+08:00")

    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    out = tmp_path / "_index_by_policy"

    project_pages(res.edges, raw_index, out)
    first = {p.name: p.read_bytes() for p in out.glob("_rev_*.md")}

    project_pages(res.edges, raw_index, out)
    second = {p.name: p.read_bytes() for p in out.glob("_rev_*.md")}

    assert first.keys() == second.keys()
    for name in first:
        assert first[name] == second[name], f"{name} 两次不一致"


def test_full_regen_removes_stale(sem_jsonl, hpr_jsonl, raw_index, tmp_path):
    """全量重生:已有的旧 _rev_*.md 被清空(不残留 stale)。"""
    out = tmp_path / "_index_by_policy"
    out.mkdir(parents=True)
    stale = out / "_rev_P_STALE_xxxx.md"
    stale.write_text("旧的脏页", encoding="utf-8")

    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    stats = project_pages(res.edges, raw_index, out)
    assert not stale.exists()
    assert stats["old_removed"] == 1


def test_safety_gate_rejects_bad_dir(raw_index, tmp_path):
    """安全闸:输出目录路径不含 _index_by_policy → 拒绝(防误删)。"""
    import pytest

    edges = [RelEdge("P_2026_GD_aaaa", "P_2026_MIIT_13", "derives_from", 0.9)]
    bad = tmp_path / "some_other_dir"
    with pytest.raises(SystemExit):
        project_pages(edges, raw_index, bad)


def test_naming_table_mapping(raw_index, tmp_path):
    """出向→入向命名表映射正确(抽 supersedes/derives_from/references 验证)。"""
    edges = [
        RelEdge("P_2026_NEA_cccc", "P_2025_NDRC_bbbb", "supersedes", 0.95),
        RelEdge("P_2026_GD_aaaa", "P_2026_MIIT_13", "derives_from", 0.9),
        RelEdge("P_2026_GD_aaaa", "P_2025_NDRC_bbbb", "references", 0.8),
    ]
    out = _project(edges, raw_index, tmp_path)

    # target P_2025_NDRC_bbbb 入向:被废止 (superseded_by) + 被引用 (referenced_by)
    bbbb = (out / "_rev_P_2025_NDRC_bbbb.md").read_text(encoding="utf-8")
    assert "被废止 (superseded_by)" in bbbb
    assert "被引用 (referenced_by)" in bbbb

    # target P_2026_MIIT_13 入向:被落地 (landed_by)
    miit = (out / "_rev_P_2026_MIIT_13.md").read_text(encoding="utf-8")
    assert "被落地 (landed_by)" in miit

    # source P_2026_NEA_cccc 出向:废止了
    cccc = (out / "_rev_P_2026_NEA_cccc.md").read_text(encoding="utf-8")
    assert "废止了" in cccc


def test_frontmatter_counts(raw_index, tmp_path):
    """frontmatter 含 policy_id/title/inbound/outbound count/last_updated。"""
    import yaml

    edges = [
        RelEdge("P_2026_NEA_cccc", "P_2025_NDRC_bbbb", "supersedes", 0.95),
        RelEdge("P_2026_GD_aaaa", "P_2025_NDRC_bbbb", "references", 0.8),
    ]
    out = _project(edges, raw_index, tmp_path)
    text = (out / "_rev_P_2025_NDRC_bbbb.md").read_text(encoding="utf-8")
    fm_block = text.split("---", 2)[1]
    fm = yaml.safe_load(fm_block)
    assert fm["policy_id"] == "P_2025_NDRC_bbbb"
    assert fm["title"] == "被废止的旧政策"
    assert fm["inbound_edge_count"] == 2  # 被 cccc supersedes + 被 aaaa references
    assert fm["outbound_edge_count"] == 0
    assert "last_updated" in fm
