from scripts.service.l1_status import (
    L1Status, read_status, set_running, set_idle, is_running,
)

def test_read_missing_defaults_idle(tmp_path):
    st = read_status(tmp_path / "l1_status.json")
    assert st.status == "idle"
    assert st.pids_collected == []

def test_set_running_then_read(tmp_path):
    p = tmp_path / "l1_status.json"
    set_running(p, started_at="2026-06-06T09:00:00")
    st = read_status(p)
    assert st.status == "running"
    assert st.started_at == "2026-06-06T09:00:00"
    assert is_running(p) is True

def test_set_idle_records_pids(tmp_path):
    p = tmp_path / "l1_status.json"
    set_running(p, started_at="2026-06-06T09:00:00")
    set_idle(p, completed_at="2026-06-06T09:30:00", pids_collected=["P_A", "P_B"])
    st = read_status(p)
    assert st.status == "idle"
    assert st.completed_at == "2026-06-06T09:30:00"
    assert st.pids_collected == ["P_A", "P_B"]
    assert is_running(p) is False
