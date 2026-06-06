"""run.preview 编排 + API 视图(canonical jsonl + 邻接索引)测试。"""
from __future__ import annotations

import json

from scripts.analysis_relation_views.run import run_preview


def test_preview_writes_both_views_no_vault(sem_jsonl, hpr_jsonl, tiny_vault, tmp_path):
    vault, _ = tiny_vault
    out_root = tmp_path / "relation_views_preview"
    summary = run_preview(vault, sem_jsonl, hpr_jsonl, out_root)

    # API 视图两文件
    canonical = out_root / "relations_canonical.jsonl"
    adjacency = out_root / "_index_by_policy.json"
    assert canonical.exists()
    assert adjacency.exists()

    # OB 视图目录(含安全闸需要的 _index_by_policy 路径)
    ob_dir = out_root / "_index_by_policy"
    assert ob_dir.is_dir()
    assert list(ob_dir.glob("_rev_*.md"))

    # 全程未写 vault
    vault_files_after = list(vault.rglob("_rev_*.md"))
    assert vault_files_after == []

    assert summary["dangling_dropped"] == 2
    assert summary["canonical_edge_count"] == 4
    assert summary["notes"] == [
        "no_vault_write", "no_raw_write", "no_apply", "dangling_filtered"
    ]


def test_canonical_jsonl_rows_valid(sem_jsonl, hpr_jsonl, tiny_vault, tmp_path):
    vault, _ = tiny_vault
    out_root = tmp_path / "rv"
    run_preview(vault, sem_jsonl, hpr_jsonl, out_root)
    rows = [
        json.loads(l)
        for l in (out_root / "relations_canonical.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    assert len(rows) == 4
    for r in rows:
        assert set(r) >= {"from", "to", "rel", "confidence"}


def test_adjacency_index_structure(sem_jsonl, hpr_jsonl, tiny_vault, tmp_path):
    vault, _ = tiny_vault
    out_root = tmp_path / "rv"
    run_preview(vault, sem_jsonl, hpr_jsonl, out_root)
    idx = json.loads((out_root / "_index_by_policy.json").read_text(encoding="utf-8"))
    # P_2025_NDRC_bbbb 被 supersedes + aligns_with + references 指向 = 3 入向
    assert len(idx["P_2025_NDRC_bbbb"]["inbound"]) == 3
    rels = {r["rel"] for r in idx["P_2025_NDRC_bbbb"]["inbound"]}
    assert rels == {"supersedes", "aligns_with", "references"}


def test_preview_idempotent(sem_jsonl, hpr_jsonl, tiny_vault, tmp_path, monkeypatch):
    """run_preview 连跑两次,_rev_*.md 与 canonical jsonl 字节一致。"""
    import scripts.analysis_relation_views.ob_projector as ob

    monkeypatch.setattr(ob, "_now_iso", lambda: "2026-06-06T00:00:00+08:00")
    vault, _ = tiny_vault
    out_root = tmp_path / "rv"

    run_preview(vault, sem_jsonl, hpr_jsonl, out_root)
    first_pages = {p.name: p.read_bytes() for p in (out_root / "_index_by_policy").glob("_rev_*.md")}
    first_canon = (out_root / "relations_canonical.jsonl").read_bytes()

    run_preview(vault, sem_jsonl, hpr_jsonl, out_root)
    second_pages = {p.name: p.read_bytes() for p in (out_root / "_index_by_policy").glob("_rev_*.md")}
    second_canon = (out_root / "relations_canonical.jsonl").read_bytes()

    assert first_pages == second_pages
    assert first_canon == second_canon
