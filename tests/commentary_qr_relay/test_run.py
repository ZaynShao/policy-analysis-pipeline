from dataclasses import dataclass

from scripts.l1_collect.commentary_ingest.qr_relay.run import QRRelayConfig, relay_once


@dataclass
class Status:
    valid: bool
    account_name: str = ""
    detail: str = ""


class FakeDetector:
    def __init__(self):
        self.calls = 0

    def __call__(self, db_path):
        self.calls += 1
        return Status(
            valid=self.calls >= 2,
            account_name="微信读书",
            detail="token 失效" if self.calls == 1 else "token 有效",
        )


class FakeLogin:
    def create_login_url(self):
        return type("Login", (), {"uuid": "uuid-1", "scan_url": "https://scan"})()

    def poll_until_success(self, uuid, timeout_seconds=0, interval_seconds=0, sleeper=None):
        return {"ok": True, "uuid": uuid}


class FakeAdapter:
    def __init__(self):
        self.pushed = False
        self.texts = []

    def push_qr(self, image_path, caption, target):
        self.pushed = image_path.exists() and "微信读书" in caption and target == "dm-1"
        return self.pushed

    def push_text(self, message, target):
        self.texts.append((message, target))
        return True


class RaisingAdapter:
    def push_qr(self, image_path, caption, target):
        raise RuntimeError("discord unavailable")


class TimeoutLogin(FakeLogin):
    def poll_until_success(self, uuid, timeout_seconds=0, interval_seconds=0, sleeper=None):
        raise TimeoutError(f"timeout for {uuid}")


def test_relay_once_generates_pushes_polls_and_confirms_valid(tmp_path):
    detector = FakeDetector()
    adapter = FakeAdapter()

    result = relay_once(
        QRRelayConfig(db_path=tmp_path / "db.sqlite", qr_dir=tmp_path, target="dm-1"),
        detector=detector,
        login_client=FakeLogin(),
        adapter=adapter,
        qr_renderer=lambda _scan_url, output_path: output_path.write_bytes(b"qr") or output_path,
        sleeper=lambda _: None,
    )

    assert result.relayed is True
    assert result.restored is True
    assert adapter.pushed is True
    assert detector.calls == 2
    assert adapter.texts == [("[policy-pipeline] 微信读书扫码已确认,wewe-rss token 已恢复。", "dm-1")]


def test_relay_once_notifies_timeout_after_qr_push(tmp_path, monkeypatch):
    notices = []
    monkeypatch.setattr(
        "scripts.l1_collect.commentary_ingest.qr_relay.run._fallback_notice",
        lambda caption, config, qr_path: notices.append((caption, qr_path)),
    )
    adapter = FakeAdapter()

    result = relay_once(
        QRRelayConfig(db_path=tmp_path / "db.sqlite", qr_dir=tmp_path, target="dm-1"),
        detector=FakeDetector(),
        login_client=TimeoutLogin(),
        adapter=adapter,
        qr_renderer=lambda _scan_url, output_path: output_path.write_bytes(b"qr") or output_path,
        sleeper=lambda _: None,
    )

    assert result.relayed is True
    assert result.restored is False
    assert result.detail == "login poll timed out"
    assert adapter.texts == [("[policy-pipeline] 微信读书扫码超时,wewe-rss token 未恢复。", "dm-1")]
    assert notices


def test_relay_once_falls_back_when_openclaw_push_raises(tmp_path, monkeypatch):
    notices = []
    monkeypatch.setattr(
        "scripts.l1_collect.commentary_ingest.qr_relay.run._fallback_notice",
        lambda caption, config, qr_path: notices.append((caption, qr_path)),
    )

    result = relay_once(
        QRRelayConfig(db_path=tmp_path / "db.sqlite", qr_dir=tmp_path, target="dm-1"),
        detector=FakeDetector(),
        login_client=FakeLogin(),
        adapter=RaisingAdapter(),
        qr_renderer=lambda _scan_url, output_path: output_path.write_bytes(b"qr") or output_path,
        sleeper=lambda _: None,
    )

    assert result.relayed is False
    assert result.restored is False
    assert result.detail == "QR push failed; fallback alert sent"
    assert notices
