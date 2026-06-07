from pathlib import Path

from scripts.l1_collect.commentary_ingest.qr_relay.daily_check import run_daily_check
from scripts.l1_collect.commentary_ingest.qr_relay.detector import TokenStatus


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
