"""canonical 合并器 + 邻接索引 测试。"""
from __future__ import annotations

from scripts.analysis_relation_views.merge import build_adjacency, merge_edges
from scripts.analysis_relation_views.models import RelEdge


def test_dangling_endpoints_dropped(sem_jsonl, hpr_jsonl, raw_index):
    """端点 pid 不在 raw 的边被剔,不进边集(代码判,不硬编 pid)。"""
    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    # sem 有 1 条 dangling(to=P_9999),hpr 有 1 条(from=P_0000)
    assert res.dangling_dropped == 2
    all_pids = {e.from_id for e in res.edges} | {e.to_id for e in res.edges}
    assert "P_9999_GONE_zzzz" not in all_pids
    assert "P_0000_GHOST_yyyy" not in all_pids


def test_no_dangling_pid_in_canonical(sem_jsonl, hpr_jsonl, raw_index):
    raw_pids = set(raw_index.keys())
    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    for e in res.edges:
        assert e.from_id in raw_pids
        assert e.to_id in raw_pids


def test_merged_counts_by_relation(sem_jsonl, hpr_jsonl, raw_index):
    res = merge_edges(sem_jsonl, hpr_jsonl, raw_index)
    # 剩 4 条有效边:derives_from, aligns_with (sem) + supersedes, references (hpr)
    assert len(res.edges) == 4
    assert res.by_rel == {
        "derives_from": 1,
        "aligns_with": 1,
        "supersedes": 1,
        "references": 1,
    }


def test_dedup_same_from_to_rel(raw_index, tmp_path):
    """同 (from,to,rel) 跨源重复 → 合并为一条,保留高 confidence。"""
    import json

    sem = tmp_path / "s.jsonl"
    hpr = tmp_path / "h.jsonl"
    sem.write_text(
        json.dumps(
            {"from": "P_2026_GD_aaaa", "to": "P_2026_MIIT_13", "rel": "derives_from",
             "confidence": 0.7, "judge_reason": "低"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    hpr.write_text(
        json.dumps(
            {"from": "P_2026_GD_aaaa", "to": "P_2026_MIIT_13", "rel": "derives_from",
             "confidence": 0.95, "evidence": "高"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    res = merge_edges(sem, hpr, raw_index)
    assert len(res.edges) == 1
    assert res.duplicates_merged == 1
    assert res.edges[0].confidence == 0.95  # 保留高 confidence


def test_invalid_rel_dropped(raw_index, tmp_path):
    import json

    sem = tmp_path / "s.jsonl"
    hpr = tmp_path / "h.jsonl"
    sem.write_text(
        json.dumps(
            {"from": "P_2026_GD_aaaa", "to": "P_2026_MIIT_13", "rel": "NOT_A_REL",
             "confidence": 0.9},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    hpr.write_text("", encoding="utf-8")
    res = merge_edges(sem, hpr, raw_index)
    assert res.invalid_rel_dropped == 1
    assert res.edges == []


def test_adjacency_index_inbound_outbound():
    edges = [
        RelEdge("P_A", "P_B", "derives_from", 0.9),
        RelEdge("P_A", "P_C", "references", 0.8),
    ]
    idx = build_adjacency(edges)
    assert idx["P_A"]["outbound"] == [
        {"to": "P_B", "rel": "derives_from", "confidence": 0.9},
        {"to": "P_C", "rel": "references", "confidence": 0.8},
    ]
    assert idx["P_B"]["inbound"] == [
        {"from": "P_A", "rel": "derives_from", "confidence": 0.9}
    ]
    assert idx["P_B"]["outbound"] == []
