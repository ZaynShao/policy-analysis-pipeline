from pathlib import Path
import json
from datetime import datetime, timedelta, timezone

from scripts.l1_collect.commentary_ingest.qr_relay.daily_check import run_daily_check
from scripts.l1_collect.commentary_ingest.qr_relay.detector import TokenStatus
from scripts.l1_collect.commentary_ingest.qr_relay.run import RelayResult


class FakeAdapter:
    def __init__(self):
        self.qrs = []

    def push_qr(self, image_path, caption, target):
        self.qrs.append((image_path, caption, target))
        return True

    def push_text(self, message, target):
        return True


class FakeLoginClient:
    def create_login_url(self):
        return type(
            "Login",
            (),
            {
                "uuid": "uuid-1",
                "scan_url": "https://open.weixin.qq.com/connect/confirm?uuid=uuid-1",
            },
        )()

    def poll_until_success(self, uuid, **kwargs):
        return {"status": "confirmed"}


def test_daily_check_does_not_relay_when_feed_valid(tmp_path):
    calls = []

    result = run_daily_check(
        db_path=tmp_path / "wewe.db",
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(True, "account", "ok"),
        relay=lambda *_args, **_kwargs: calls.append("relay"),
    )

    assert result.relayed is False
    assert result.restored is True
    assert calls == []


def test_daily_check_relays_when_token_invalid_even_if_feed_valid(tmp_path):
    captured = []

    def fake_relay(config, **_kwargs):
        captured.append(config)
        return RelayResult(True, True, False, "pushed")

    result = run_daily_check(
        db_path=tmp_path / "wewe.db",
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(True, "account", "feed ok"),
        token_checker=lambda db_path: TokenStatus(False, "account", f"token invalid: {db_path.name}"),
        relay=fake_relay,
    )

    assert result.relayed is True
    assert result.restored is False
    assert captured


def test_daily_check_relays_when_feed_invalid(tmp_path):
    adapter = FakeAdapter()

    result = run_daily_check(
        db_path=Path(tmp_path / "wewe.db"),
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(False, "account", "401"),
        login_client=FakeLoginClient(),
        adapter=adapter,
        qr_renderer=lambda _scan_url, path: Path(path).write_bytes(b"png") or Path(path),
        sleeper=lambda _seconds: None,
    )

    assert result.relayed is True
    assert result.qr_path == tmp_path / "wewe-login-uuid-1.png"
    assert adapter.qrs


def test_outage_note_first_time(tmp_path):
    now = datetime(2026, 6, 8, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    captured = []

    def fake_relay(config, **_kwargs):
        captured.append(config)
        return RelayResult(True, True, False, "pushed")

    run_daily_check(
        db_path=tmp_path / "wewe.db",
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(False, "account", "401"),
        relay=fake_relay,
        now=now,
    )

    assert "第 1 次" in captured[0].note
    state = json.loads((tmp_path / "relay_outage.json").read_text(encoding="utf-8"))
    assert state["count"] == 1


def test_outage_note_increments(tmp_path):
    now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    first_down = now - timedelta(hours=2)
    (tmp_path / "relay_outage.json").write_text(
        json.dumps({"first_down_at": first_down.isoformat(), "count": 1}),
        encoding="utf-8",
    )
    captured = []

    def fake_relay(config, **_kwargs):
        captured.append(config)
        return RelayResult(True, True, False, "pushed")

    run_daily_check(
        db_path=tmp_path / "wewe.db",
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(False, "account", "401"),
        relay=fake_relay,
        now=now,
    )

    assert "第 2 次" in captured[0].note
    assert "约 2h" in captured[0].note
    state = json.loads((tmp_path / "relay_outage.json").read_text(encoding="utf-8"))
    assert state["count"] == 2
    assert state["first_down_at"] == first_down.isoformat()


def test_outage_cleared_on_valid(tmp_path):
    (tmp_path / "relay_outage.json").write_text(
        json.dumps({"first_down_at": "2026-06-08T10:00:00+08:00", "count": 2}),
        encoding="utf-8",
    )
    calls = []

    run_daily_check(
        db_path=tmp_path / "wewe.db",
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(True, "account", "ok"),
        relay=lambda *_args, **_kwargs: calls.append("relay"),
    )

    assert not (tmp_path / "relay_outage.json").exists()
    assert calls == []


def test_outage_cleared_when_relay_restores(tmp_path):
    (tmp_path / "relay_outage.json").write_text(
        json.dumps({"first_down_at": "2026-06-08T10:00:00+08:00", "count": 2}),
        encoding="utf-8",
    )

    def fake_relay(config, **_kwargs):
        return RelayResult(True, True, True, "ok")

    run_daily_check(
        db_path=tmp_path / "wewe.db",
        qr_dir=tmp_path,
        target="target-1",
        wewe_base_url="http://localhost:4000",
        auth_code="auth-code",
        feed_checker=lambda base_url, auth_code: TokenStatus(False, "account", "401"),
        relay=fake_relay,
        now=datetime(2026, 6, 8, 12, 0, tzinfo=timezone(timedelta(hours=8))),
    )

    assert not (tmp_path / "relay_outage.json").exists()
