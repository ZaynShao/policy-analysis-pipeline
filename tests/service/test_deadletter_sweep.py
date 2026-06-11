import json

from scripts.service import deadletter_sweep
from scripts.service.l2_queue import read_queue


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_sweep_requeues_unique_pids_rotates_deadletter_and_updates_history(tmp_path):
    _write_jsonl(
        tmp_path / "l2_failures.jsonl",
        [
            {"pid": "P_A", "error": "a1", "ts": "t1"},
            {"pid": "P_A", "error": "a2", "ts": "t2"},
            {"pid": "P_B", "error": "b", "ts": "t3"},
        ],
    )

    rc = deadletter_sweep.main(["--state-dir", str(tmp_path)])

    queue = read_queue(tmp_path / "l2_queue.jsonl")
    history = json.loads((tmp_path / "l2_sweep_history.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert [item.pid for item in queue] == ["P_A", "P_B"]
    assert {item.trigger for item in queue} == {"sweep"}
    assert _read_jsonl(tmp_path / "l2_failures.jsonl") == []
    assert [row["pid"] for row in _read_jsonl(tmp_path / "l2_failures.archived.jsonl")] == [
        "P_A",
        "P_A",
        "P_B",
    ]
    assert history == {"P_A": 1, "P_B": 1}


def test_plan_sweep_sends_pid_at_retry_limit_to_givenup():
    records = [
        {"pid": "P_DONE", "error": "old", "ts": "t1"},
        {"pid": "P_NEW", "error": "new", "ts": "t2"},
    ]

    requeue, givenup, history = deadletter_sweep.plan_sweep(
        records, {"P_DONE": 2}, max_retries=2
    )

    assert requeue == ["P_NEW"]
    assert givenup == ["P_DONE"]
    assert history == {"P_DONE": 2, "P_NEW": 1}


def test_sweep_cap_leaves_unprocessed_records_in_deadletter(tmp_path):
    _write_jsonl(
        tmp_path / "l2_failures.jsonl",
        [
            {"pid": "P_A", "error": "a", "ts": "t1"},
            {"pid": "P_B", "error": "b", "ts": "t2"},
            {"pid": "P_C", "error": "c", "ts": "t3"},
        ],
    )

    rc = deadletter_sweep.main(["--state-dir", str(tmp_path), "--cap", "1"])

    assert rc == 0
    assert [item.pid for item in read_queue(tmp_path / "l2_queue.jsonl")] == ["P_A"]
    assert [row["pid"] for row in _read_jsonl(tmp_path / "l2_failures.jsonl")] == [
        "P_B",
        "P_C",
    ]
    assert [row["pid"] for row in _read_jsonl(tmp_path / "l2_failures.archived.jsonl")] == [
        "P_A"
    ]


def test_sweep_noops_when_deadletter_missing_or_empty(tmp_path, capsys):
    rc = deadletter_sweep.main(["--state-dir", str(tmp_path)])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out == {"swept": 0}
    assert not (tmp_path / "l2_queue.jsonl").exists()


def test_sweep_notifies_givenup_pids(tmp_path, monkeypatch, capsys):
    _write_jsonl(
        tmp_path / "l2_failures.jsonl",
        [{"pid": "P_DONE", "error": "old", "ts": "t1"}],
    )
    (tmp_path / "l2_sweep_history.json").write_text(
        json.dumps({"P_DONE": 2}),
        encoding="utf-8",
    )
    sent = []
    monkeypatch.setattr(deadletter_sweep.notify, "send_text", lambda msg: sent.append(msg) or True)

    rc = deadletter_sweep.main(["--state-dir", str(tmp_path), "--max-retries", "2"])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(sent) == 1
    assert "P_DONE" in sent[0]
    assert out["givenup"] == 1
    assert read_queue(tmp_path / "l2_queue.jsonl") == []
