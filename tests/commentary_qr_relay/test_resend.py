from dataclasses import dataclass
import sys

from scripts.l1_collect.commentary_ingest.qr_relay.resend import (
    _spawn_relay,
    resend_wewe_qr,
)


@dataclass
class Status:
    valid: bool
    detail: str = ""
    account_name: str = ""


def test_resend_wewe_qr_noops_when_token_is_valid(tmp_path):
    spawn_calls = []

    result = resend_wewe_qr(
        tmp_path / "wewe.sqlite",
        detector=lambda db_path: Status(valid=True, detail=f"checked {db_path}"),
        spawn=lambda: spawn_calls.append("spawned"),
    )

    assert result == {
        "action": "noop",
        "valid": True,
        "message": "token 仍有效,无需重发",
    }
    assert spawn_calls == []


def test_resend_wewe_qr_spawns_relay_when_token_is_invalid(tmp_path):
    spawn_calls = []

    result = resend_wewe_qr(
        tmp_path / "wewe.sqlite",
        detector=lambda db_path: Status(valid=False, detail="expired"),
        spawn=lambda: spawn_calls.append("spawned"),
    )

    assert result == {
        "action": "resent",
        "valid": False,
        "message": "已重新推送二维码,请扫描;扫码成功会收到确认",
    }
    assert spawn_calls == ["spawned"]


def test_default_spawn_starts_existing_relay_detached(monkeypatch, tmp_path):
    popen_calls = []
    log_path = tmp_path / "qr_relay.log"
    expected_env = {"WEWE_DB_PATH": "/tmp/wewe.sqlite", "QR_RELAY_LOG": str(log_path)}
    monkeypatch.setattr("scripts.l1_collect.commentary_ingest.qr_relay.resend.os.environ", expected_env)

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return object()

    _spawn_relay(popen=fake_popen)

    args, kwargs = popen_calls[0]
    assert args[0] == [
        sys.executable,
        "-m",
        "scripts.l1_collect.commentary_ingest.qr_relay.run",
    ]
    assert kwargs["start_new_session"] is True
    assert kwargs["env"] is expected_env
    assert kwargs["stdout"] is kwargs["stderr"]
    assert not kwargs["stdout"].closed
