from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.service import relations_increment as ri


def _git(cwd: Path, args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_policy(
    vault: Path,
    pid: str,
    title: str,
    *,
    issuer: str = "测试机关",
    date: str = "2024-01-01",
    region_level: str = "省",
    region_name: str = "测试省",
    body: str = "## 政策原文\n正文。",
) -> None:
    path = vault / "0_raw" / "policies" / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"id: {pid}\n"
        f"title: {title}\n"
        f"official_number: {pid[-4:]}\n"
        f"issuer:\n  - {issuer}\n"
        f"date: '{date}'\n"
        "region:\n"
        f"  level: {region_level}\n"
        "  code: '000000'\n"
        f"  name: {region_name}\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _write_business_view(vault: Path, pid: str, theme: str = "charging_infra") -> None:
    path = vault / "_meta" / "business_view" / f"{pid}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"pid: {pid}\n"
        f"themes:\n  - {theme}\n"
        f"primary_theme: {theme}\n"
        "重要性: 4\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture
def increment_vault(tmp_path: Path) -> tuple[Path, str]:
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, ["init", "-b", "main"])
    _git(vault, ["config", "user.name", "test"])
    _git(vault, ["config", "user.email", "test@example.com"])

    _write_policy(
        vault,
        "P_2024_TEST_old1",
        "旧政策一",
        date="2024-01-01",
        body="## 政策原文\n旧政策一正文。",
    )
    _write_policy(
        vault,
        "P_2024_TEST_old2",
        "旧政策二",
        date="2024-02-01",
        body="## 政策原文\n旧政策二正文。",
    )
    _write_business_view(vault, "P_2024_TEST_old1")
    _write_business_view(vault, "P_2024_TEST_old2")
    _git(vault, ["add", "0_raw", "_meta"])
    _git(vault, ["commit", "-m", "old policies"])
    old_commit = _git(vault, ["rev-parse", "HEAD"])

    _write_policy(
        vault,
        "P_2025_TEST_new1",
        "新政策一",
        date="2025-01-01",
        body="## 政策原文\n新政策一正文。",
    )
    _write_business_view(vault, "P_2025_TEST_new1")
    _git(vault, ["add", "0_raw", "_meta"])
    _git(vault, ["commit", "-m", "new policy"])

    rel_dir = vault / "1_extracted" / "relations"
    _write_jsonl(
        rel_dir / "relations_canonical.jsonl",
        [
            {
                "from": "P_2024_TEST_old2",
                "to": "P_2024_TEST_old1",
                "rel": "iterates",
                "confidence": 0.9,
                "evidence": "old",
                "source": "seed",
            }
        ],
    )
    (rel_dir / "_index_by_policy").mkdir(parents=True)
    (rel_dir / "_index_by_policy.json").write_text("{}\n", encoding="utf-8")
    (rel_dir / "_index_by_policy" / "_rev_P_2024_TEST_old1.md").write_text("old\n", encoding="utf-8")
    return vault, old_commit


class AcceptJudge:
    model = "fake-accept"

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        return json.dumps({"decision": "accept", "confidence": 0.88, "reason": "fixture accept"})


class NoJudge:
    model = "no-judge"

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        raise AssertionError("judge should not be called")


def test_select_new_pids_preserves_tracked_order():
    ledger = {"covered": ["P2", "P4"]}
    assert ri.select_new_pids(["P1", "P2", "P3"], ledger) == ["P1", "P3"]
    assert ri.select_new_pids(["P2", "P4"], ledger) == []


def test_filter_increment_candidates_keeps_new_endpoint_and_unjudged_only():
    rows = [
        {"candidate_id": "SRC_keep_from", "from": "P_new", "to": "P_old", "rel": "iterates"},
        {"candidate_id": "SRC_keep_to", "from": "P_old", "to": "P_new", "rel": "iterates"},
        {"candidate_id": "SRC_old_only", "from": "P_old1", "to": "P_old2", "rel": "iterates"},
        {"candidate_id": "SRC_judged", "from": "P_new", "to": "P_old2", "rel": "iterates"},
    ]
    kept = ri.filter_increment_candidates(rows, {"P_new"}, {"SRC_judged"})
    assert [row["candidate_id"] for row in kept] == ["SRC_keep_from", "SRC_keep_to"]


def test_init_ledger_reads_policy_ids_from_git_archive(increment_vault: tuple[Path, str], tmp_path: Path):
    vault, old_commit = increment_vault
    state_dir = tmp_path / "state"
    rc = ri.init_ledger(vault, state_dir, old_commit)
    assert rc == {"covered": 2}
    ledger = json.loads((state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8"))
    assert ledger["covered"] == ["P_2024_TEST_old1", "P_2024_TEST_old2"]


def test_run_applies_increment_and_updates_ledgers(increment_vault: tuple[Path, str], tmp_path: Path):
    vault, old_commit = increment_vault
    state_dir = tmp_path / "state"
    ri.init_ledger(vault, state_dir, old_commit)
    _write_jsonl(
        state_dir / "sem_accepted_cumulative.jsonl",
        [
            {
                "candidate_id": "SRC_seed",
                "from": "P_2024_TEST_old2",
                "to": "P_2024_TEST_old1",
                "rel": "iterates",
                "confidence": 0.9,
                "judge_reason": "seed",
            }
        ],
    )

    summary = ri.run_increment(vault, state_dir, "fake", "openai", dry_run=False, judge_client=AcceptJudge())

    assert summary["new_pids"] == 1
    assert summary["judged"] > 0
    assert summary["accepted"] == summary["judged"]
    assert summary["applied"] is True
    ledger = json.loads((state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8"))
    assert ledger["covered"] == ["P_2024_TEST_old1", "P_2024_TEST_old2", "P_2025_TEST_new1"]
    assert len(_read_jsonl(state_dir / "sem_accepted_cumulative.jsonl")) > 1
    assert len(_read_jsonl(state_dir / "relations_judged_ledger.jsonl")) == summary["judged"]
    assert (vault / "1_extracted" / "relations" / "relations_canonical.jsonl").exists()
    assert (vault / "1_extracted" / "relations" / "_index_by_policy.json").exists()
    assert (vault / "1_extracted" / "relations" / "_index_by_policy").is_dir()


def test_run_rejects_collapsed_preview_without_touching_vault_or_ledger(
    increment_vault: tuple[Path, str], tmp_path: Path
):
    vault, old_commit = increment_vault
    state_dir = tmp_path / "state"
    ri.init_ledger(vault, state_dir, old_commit)
    old_ledger = (state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8")
    rel_dir = vault / "1_extracted" / "relations"
    _write_jsonl(
        rel_dir / "relations_canonical.jsonl",
        [
            {"from": f"P{i}", "to": f"Q{i}", "rel": "references", "confidence": 1.0}
            for i in range(5)
        ],
    )
    old_vault = (rel_dir / "relations_canonical.jsonl").read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        ri.run_increment(vault, state_dir, "fake", "openai", dry_run=False, judge_client=AcceptJudge())

    assert exc.value.code == 1
    assert (rel_dir / "relations_canonical.jsonl").read_text(encoding="utf-8") == old_vault
    assert (state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8") == old_ledger


def test_dry_run_skips_vault_and_ledger_updates(increment_vault: tuple[Path, str], tmp_path: Path):
    vault, old_commit = increment_vault
    state_dir = tmp_path / "state"
    ri.init_ledger(vault, state_dir, old_commit)
    old_ledger = (state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8")
    old_vault = (vault / "1_extracted" / "relations" / "relations_canonical.jsonl").read_text(encoding="utf-8")

    summary = ri.run_increment(vault, state_dir, "fake", "openai", dry_run=True, judge_client=AcceptJudge())

    assert summary["applied"] is False
    assert (state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8") == old_ledger
    assert (vault / "1_extracted" / "relations" / "relations_canonical.jsonl").read_text(encoding="utf-8") == old_vault


def test_empty_increment_exits_before_judge(increment_vault: tuple[Path, str], tmp_path: Path):
    vault, _old_commit = increment_vault
    state_dir = tmp_path / "state"
    ri.write_pid_ledger(state_dir / "relations_pid_ledger.json", [
        "P_2024_TEST_old1",
        "P_2024_TEST_old2",
        "P_2025_TEST_new1",
    ])
    old_ledger = (state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8")

    summary = ri.run_increment(vault, state_dir, "fake", "openai", dry_run=False, judge_client=NoJudge())

    assert summary == {"new_pids": 0}
    assert (state_dir / "relations_pid_ledger.json").read_text(encoding="utf-8") == old_ledger
