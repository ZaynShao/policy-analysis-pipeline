from scripts.service import notify


class FakeAdapter:
    def __init__(self):
        self.sent = []

    def push_text(self, message, target):
        self.sent.append((message, target))
        return True


def test_send_text_pushes_via_adapter_with_env_target(monkeypatch):
    monkeypatch.setenv("OPENCLAW_IM_TARGET", "ou_x")
    fake = FakeAdapter()
    ok = notify.send_text("hello", adapter=fake)
    assert ok is True
    assert fake.sent == [("hello", "ou_x")]


def test_send_text_returns_false_when_env_missing(monkeypatch):
    monkeypatch.delenv("OPENCLAW_CHANNEL", raising=False)
    monkeypatch.delenv("OPENCLAW_IM_TARGET", raising=False)
    assert notify.send_text("hello") is False


def test_send_text_never_raises_on_adapter_error(monkeypatch):
    monkeypatch.setenv("OPENCLAW_IM_TARGET", "ou_x")

    class Boom:
        def push_text(self, message, target):
            raise RuntimeError("openclaw down")

    assert notify.send_text("hello", adapter=Boom()) is False
