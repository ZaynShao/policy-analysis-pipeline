import json

from scripts.service import deadletter_alert


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_check_growth_alerts_when_deadletter_count_grows(tmp_path):
    dead = tmp_path / "l2_failures.jsonl"
    state = tmp_path / "deadletter_alert_state.json"
    _write_jsonl(
        dead,
        [
            {"pid": "P_OLD", "error": "old failure", "ts": "t1"},
            {"pid": "P_NEW", "error": "new failure", "ts": "t2"},
        ],
    )

    msg = deadletter_alert.check_growth(dead, state)

    assert msg is not None
    assert "0→2" in msg
    assert "P_NEW" in msg
    assert json.loads(state.read_text(encoding="utf-8"))["last_count"] == 2


def test_check_growth_no_alert_when_count_unchanged_but_checked_at_updates(tmp_path):
    dead = tmp_path / "l2_failures.jsonl"
    state = tmp_path / "deadletter_alert_state.json"
    _write_jsonl(dead, [{"pid": "P_A", "error": "failure", "ts": "t1"}])
    state.write_text(
        json.dumps({"last_count": 1, "checked_at": "old"}),
        encoding="utf-8",
    )

    msg = deadletter_alert.check_growth(dead, state)

    new_state = json.loads(state.read_text(encoding="utf-8"))
    assert msg is None
    assert new_state["last_count"] == 1
    assert new_state["checked_at"] != "old"


def test_check_growth_missing_deadletter_counts_as_zero(tmp_path):
    state = tmp_path / "deadletter_alert_state.json"

    msg = deadletter_alert.check_growth(tmp_path / "l2_failures.jsonl", state)

    assert msg is None
    assert json.loads(state.read_text(encoding="utf-8"))["last_count"] == 0


def test_check_growth_no_alert_when_count_shrinks_after_rotation(tmp_path):
    dead = tmp_path / "l2_failures.jsonl"
    state = tmp_path / "deadletter_alert_state.json"
    _write_jsonl(dead, [{"pid": "P_LEFT", "error": "failure", "ts": "t1"}])
    state.write_text(
        json.dumps({"last_count": 5, "checked_at": "old"}),
        encoding="utf-8",
    )

    msg = deadletter_alert.check_growth(dead, state)

    assert msg is None
    assert json.loads(state.read_text(encoding="utf-8"))["last_count"] == 1


def test_cli_sends_notification_and_exits_zero(tmp_path, monkeypatch, capsys):
    _write_jsonl(
        tmp_path / "l2_failures.jsonl",
        [{"pid": "P_A", "error": "failure", "ts": "t1"}],
    )
    sent = []
    monkeypatch.setattr(deadletter_alert.notify, "send_text", lambda msg: sent.append(msg) or True)

    rc = deadletter_alert.main(["--state-dir", str(tmp_path)])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(sent) == 1
    assert out["dead_count"] == 1
    assert out["grew"] is True
    assert out["notified"] is True
