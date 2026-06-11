from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.service import summaries_increment as si


def _write_policy(
    vault: Path,
    pid: str,
    title: str,
    *,
    aliases: list[str] | None = None,
    issuer: str = "测试机关",
    date: str = "2024-01-01",
    body: str = "## 政策原文\n正文。",
) -> None:
    path = vault / "0_raw" / "policies" / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_lines = "".join(f"  - {alias}\n" for alias in (aliases or [pid]))
    path.write_text(
        "---\n"
        f"id: {pid}\n"
        "aliases:\n"
        f"{alias_lines}"
        f"title: {title}\n"
        f"issuer:\n  - {issuer}\n"
        f"date: '{date}'\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _summary_row(pid: str, extracted_at: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "policy_id": pid,
        "summary": "面向测试对象的客观摘要，说明范围、对象、截止日和数量目标。",
        "summary_one_liner": "测试摘要",
        "reading_value": "用于快速阅读",
        "extracted_at": extracted_at,
        "extracted_by": "scripts/service/summaries_increment.py",
        "extracted_model": "fixture",
    }


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    _write_policy(root, "P_new", "新政策", aliases=["P_old"], date="2025-01-01")
    _write_policy(root, "P_direct", "直配政策", date="2024-01-01")
    return root


class CountingClient:
    model = "fixture-model"

    def __init__(self, outputs: list[dict | str]):
        self.outputs = list(outputs)
        self.calls = 0

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        self.calls += 1
        out = self.outputs.pop(0)
        if isinstance(out, str):
            return out
        return json.dumps(out, ensure_ascii=False)


def test_init_ledger_dry_run_reports_without_writing(vault: Path, tmp_path: Path):
    summaries = vault / "1_extracted" / "policy_summaries.jsonl"
    original_rows = [
        _summary_row("P_direct", "2026-01-01T00:00:00+00:00"),
        _summary_row("P_old", "2026-01-02T00:00:00+00:00"),
        _summary_row("P_missing", "2026-01-03T00:00:00+00:00"),
        _summary_row("P_direct", "2026-01-04T00:00:00+00:00"),
    ]
    _write_jsonl(summaries, original_rows)

    report = si.init_ledger(vault, tmp_path / "state", apply=False)

    assert report == {
        "kept_direct": 2,
        "kept_alias": 1,
        "quarantined": 1,
        "dedup_dropped": 1,
        "covered": 2,
    }
    assert _read_jsonl(summaries) == original_rows
    assert not (tmp_path / "state" / "summaries_pid_ledger.json").exists()
    assert not (tmp_path / "state" / "summaries_quarantine.jsonl").exists()


def test_init_ledger_apply_normalizes_alias_quarantines_and_dedups(vault: Path, tmp_path: Path):
    summaries = vault / "1_extracted" / "policy_summaries.jsonl"
    _write_jsonl(
        summaries,
        [
            _summary_row("P_direct", "2026-01-01T00:00:00+00:00"),
            _summary_row("P_old", "2026-01-02T00:00:00+00:00"),
            _summary_row("P_missing", "2026-01-03T00:00:00+00:00"),
            _summary_row("P_direct", "2026-01-04T00:00:00+00:00"),
        ],
    )

    report = si.init_ledger(vault, tmp_path / "state", apply=True)

    assert report["covered"] == 2
    rows = _read_jsonl(summaries)
    rows_by_pid = {row["policy_id"]: row for row in rows}
    assert set(rows_by_pid) == {"P_new", "P_direct"}
    assert rows_by_pid["P_new"]["normalized_from"] == "P_old"
    assert rows_by_pid["P_direct"]["extracted_at"] == "2026-01-04T00:00:00+00:00"
    quarantine = _read_jsonl(tmp_path / "state" / "summaries_quarantine.jsonl")
    assert quarantine[0]["policy_id"] == "P_missing"
    assert quarantine[0]["reason"] == "policy_id_not_found"
    ledger = json.loads((tmp_path / "state" / "summaries_pid_ledger.json").read_text(encoding="utf-8"))
    assert ledger["covered"] == ["P_direct", "P_new"]


def test_run_dry_run_uses_limit_staging_cache_and_does_not_write_vault(vault: Path, tmp_path: Path):
    state = tmp_path / "state"
    si.write_pid_ledger(state / "summaries_pid_ledger.json", ["P_direct"])
    summaries = vault / "1_extracted" / "policy_summaries.jsonl"
    _write_jsonl(summaries, [_summary_row("P_direct")])
    client = CountingClient(
        [
            {
                "summary": "新政策面向测试对象，明确实施范围、适用对象、截止日和数量目标。",
                "summary_one_liner": "新政策摘要",
                "reading_value": "看适用范围",
            }
        ]
    )

    first = si.run_increment(vault, state, "fixture-model", "openai", dry_run=True, limit=1, client=client)
    second = si.run_increment(vault, state, "fixture-model", "openai", dry_run=True, limit=1, client=client)

    assert first == {"new": 1, "generated": 1, "queued": 0, "staged": 1, "applied": False}
    assert second == {"new": 1, "generated": 0, "queued": 0, "staged": 1, "applied": False}
    assert client.calls == 1
    assert [row["policy_id"] for row in _read_jsonl(state / "summaries_staging.jsonl")] == ["P_new"]
    assert _read_jsonl(summaries) == [_summary_row("P_direct")]


def test_run_program_gate_retries_then_queues(vault: Path, tmp_path: Path):
    state = tmp_path / "state"
    si.write_pid_ledger(state / "summaries_pid_ledger.json", ["P_direct"])
    _write_jsonl(vault / "1_extracted" / "policy_summaries.jsonl", [_summary_row("P_direct")])
    client = CountingClient(
        [
            {"summary": "", "summary_one_liner": "空摘要", "reading_value": "看范围"},
            {"summary": "仍然失败", "summary_one_liner": "过长" * 20, "reading_value": "看范围"},
        ]
    )

    summary = si.run_increment(vault, state, "fixture-model", "openai", dry_run=True, client=client)

    assert summary == {"new": 1, "generated": 0, "queued": 1, "staged": 0, "applied": False}
    queued = _read_jsonl(state / "summaries_review_queue.jsonl")
    assert queued[0]["policy_id"] == "P_new"
    assert "summary_one_liner" in queued[0]["reason"]
    assert client.calls == 2


def test_run_apply_appends_staged_rows_updates_ledger_and_clears_applied_staging(vault: Path, tmp_path: Path):
    state = tmp_path / "state"
    si.write_pid_ledger(state / "summaries_pid_ledger.json", ["P_direct"])
    _write_jsonl(vault / "1_extracted" / "policy_summaries.jsonl", [_summary_row("P_direct")])
    _write_jsonl(state / "summaries_staging.jsonl", [_summary_row("P_new")])

    summary = si.run_increment(vault, state, "fixture-model", "openai", dry_run=False, client=CountingClient([]))

    assert summary == {"new": 1, "generated": 0, "queued": 0, "staged": 1, "applied": True}
    assert [row["policy_id"] for row in _read_jsonl(vault / "1_extracted" / "policy_summaries.jsonl")] == [
        "P_direct",
        "P_new",
    ]
    ledger = json.loads((state / "summaries_pid_ledger.json").read_text(encoding="utf-8"))
    assert ledger["covered"] == ["P_direct", "P_new"]
    assert _read_jsonl(state / "summaries_staging.jsonl") == []


def test_run_apply_gate_rejects_duplicate_policy_id_without_writing(vault: Path, tmp_path: Path):
    state = tmp_path / "state"
    si.write_pid_ledger(state / "summaries_pid_ledger.json", ["P_direct"])
    summaries = vault / "1_extracted" / "policy_summaries.jsonl"
    _write_jsonl(summaries, [_summary_row("P_direct"), _summary_row("P_direct")])
    _write_jsonl(state / "summaries_staging.jsonl", [_summary_row("P_new")])
    before = summaries.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        si.run_increment(vault, state, "fixture-model", "openai", dry_run=False, client=CountingClient([]))

    assert exc.value.code == 1
    assert summaries.read_text(encoding="utf-8") == before
    ledger = json.loads((state / "summaries_pid_ledger.json").read_text(encoding="utf-8"))
    assert ledger["covered"] == ["P_direct"]
