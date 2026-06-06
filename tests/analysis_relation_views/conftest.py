"""共享夹具:在 tmp 里造最小 raw vault + 两源关系 jsonl。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analysis_relation_views.raw_index import load_raw_index


def _write_raw_policy(policies_dir: Path, pid: str, title: str, date: str = "2024-01-01"):
    """写一篇最小 raw 政策。file_stem = 文件名去 .md(中文哈希名风格)。"""
    stem = f"【{title}】-机构-{pid[-4:].lower()}"
    fm = (
        "---\n"
        f"id: {pid}\n"
        f"title: {title}\n"
        f"date: {date}\n"
        "---\n"
        f"正文 {title}。\n"
    )
    (policies_dir / f"{stem}.md").write_text(fm, encoding="utf-8")
    return stem


@pytest.fixture
def tiny_vault(tmp_path):
    """造一个最小 raw vault + 已知 pid。返回 (vault_path, {pid: stem})。"""
    policies = tmp_path / "vault" / "0_raw" / "policies"
    policies.mkdir(parents=True)
    stems = {}
    # 最小图谱孤岛夹具:R 被 A 通过 derives_from 指向(R=被落地的国家级、A=省级派生)
    stems["P_2026_MIIT_13"] = _write_raw_policy(
        policies, "P_2026_MIIT_13", "国家级被指向政策R", "2026-01-01"
    )
    stems["P_2026_GD_aaaa"] = _write_raw_policy(
        policies, "P_2026_GD_aaaa", "广东省派生政策A", "2026-03-01"
    )
    stems["P_2025_NDRC_bbbb"] = _write_raw_policy(
        policies, "P_2025_NDRC_bbbb", "被废止的旧政策", "2025-02-01"
    )
    stems["P_2026_NEA_cccc"] = _write_raw_policy(
        policies, "P_2026_NEA_cccc", "废止旧政策的新政策", "2026-05-01"
    )
    return tmp_path / "vault", stems


def _write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def sem_jsonl(tmp_path):
    """③-C 语义关系夹具:含 1 条 dangling(to 不在 raw)。"""
    rows = [
        # A derives_from R(R 是被落地的国家级 → R 的反链页须存在且不孤岛)
        {
            "candidate_id": "SEM_1",
            "from": "P_2026_GD_aaaa",
            "to": "P_2026_MIIT_13",
            "rel": "derives_from",
            "confidence": 0.9,
            "judge_reason": "省级落地国家级",
        },
        # 一条 aligns_with(对称类,仍按有向边渲染)
        {
            "candidate_id": "SEM_2",
            "from": "P_2026_GD_aaaa",
            "to": "P_2025_NDRC_bbbb",
            "rel": "aligns_with",
            "confidence": 0.8,
            "judge_reason": "同主题对齐",
        },
        # dangling:to 不在 raw → 必须被剔
        {
            "candidate_id": "SEM_DANGLING",
            "from": "P_2026_GD_aaaa",
            "to": "P_9999_GONE_zzzz",
            "rel": "iterates",
            "confidence": 0.7,
            "judge_reason": "指向不存在政策",
        },
    ]
    p = tmp_path / "sem.jsonl"
    _write_jsonl(p, rows)
    return p


@pytest.fixture
def hpr_jsonl(tmp_path):
    """③-B 高精度关系夹具:含 1 条 dangling(from 不在 raw)。"""
    rows = [
        # 新政策废止旧政策
        {
            "candidate_id": "HPR_1",
            "from": "P_2026_NEA_cccc",
            "to": "P_2025_NDRC_bbbb",
            "rel": "supersedes",
            "confidence": 0.95,
            "evidence": "本通知发布之日起,旧政策废止。",
        },
        # references
        {
            "candidate_id": "HPR_2",
            "from": "P_2026_GD_aaaa",
            "to": "P_2025_NDRC_bbbb",
            "rel": "references",
            "confidence": 0.9,
            "evidence": "参见旧政策第三条。",
        },
        # dangling:from 不在 raw → 必须被剔
        {
            "candidate_id": "HPR_DANGLING",
            "from": "P_0000_GHOST_yyyy",
            "to": "P_2026_MIIT_13",
            "rel": "cites_basis",
            "confidence": 0.9,
            "evidence": "来自不存在政策的引用",
        },
    ]
    p = tmp_path / "hpr.jsonl"
    _write_jsonl(p, rows)
    return p


@pytest.fixture
def raw_index(tiny_vault):
    vault, _ = tiny_vault
    return load_raw_index(vault)
