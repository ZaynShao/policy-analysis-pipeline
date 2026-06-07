import json

import pytest

from scripts.service.l2_queue import QueueItem, enqueue
from scripts.service.run_l2 import build_raw_text_for, run


def test_build_raw_text_for(tmp_path):
    vault = tmp_path / "vault"
    policies = vault / "0_raw" / "policies"
    policies.mkdir(parents=True)
    raw_text = """---
id: P_FAKE_0001
title: fake
---
## 政策原文
fake body
"""
    (policies / "anyname.md").write_text(raw_text, encoding="utf-8")

    raw_text_for = build_raw_text_for(vault)

    assert raw_text_for("P_FAKE_0001") == raw_text
    with pytest.raises(KeyError):
        raw_text_for("P_MISSING")


def test_run_wires_drain(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    enqueue(state_dir / "l2_queue.jsonl",
            QueueItem("P_FAKE_0002", "manual", "high", "t1"))
    attribution_calls = []
    sync_calls = []

    results = run(
        state_dir,
        1,
        raw_text_for=lambda pid: "RAW",
        run_attribution=lambda pid: attribution_calls.append(pid),
        run_sync=lambda: sync_calls.append("synced"),
    )

    assert attribution_calls == ["P_FAKE_0002"]
    assert sync_calls == ["synced"]
    ledger = json.loads((state_dir / "ledger.json").read_text(encoding="utf-8"))
    assert "P_FAKE_0002" in ledger
    assert len(results) == 1
    assert results[0].ok is True


def test_run_empty_queue_no_sync(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    sync_calls = []

    results = run(
        state_dir,
        1,
        raw_text_for=lambda pid: "RAW",
        run_attribution=lambda pid: None,
        run_sync=lambda: sync_calls.append("synced"),
    )

    assert sync_calls == []
    assert results == []
