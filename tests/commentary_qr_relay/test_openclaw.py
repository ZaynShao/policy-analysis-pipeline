from scripts.l1_collect.commentary_ingest.qr_relay.openclaw import (
    DiscordBotAdapter,
    OpenClawMessageAdapter,
)


class FakeResponse:
    def __init__(self, payload=None):
        self.ok = True
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, data=None, files=None, timeout=None):
        self.calls.append((url, headers, data, files, timeout))
        if url.endswith("/users/@me/channels"):
            return FakeResponse({"id": "dm-channel"})
        return FakeResponse()


def test_discord_adapter_pushes_qr_as_multipart_image(tmp_path):
    image = tmp_path / "qr.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    session = FakeSession()
    adapter = DiscordBotAdapter("bot-token", session=session)

    ok = adapter.push_qr(image, "扫码恢复 wewe-rss", "123456")

    assert ok is True
    url, headers, data, files, timeout = session.calls[0]
    assert url == "https://discord.com/api/v10/channels/123456/messages"
    assert headers == {"Authorization": "Bot bot-token"}
    assert '"content": "扫码恢复 wewe-rss"' in data["payload_json"]
    assert files["files[0]"][0] == "qr.png"
    assert timeout == 20


def test_discord_adapter_accepts_user_target_by_creating_dm_channel(tmp_path):
    image = tmp_path / "qr.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    session = FakeSession()
    adapter = DiscordBotAdapter("bot-token", session=session)

    ok = adapter.push_qr(image, "扫码恢复 wewe-rss", "user:1510522333142712322")

    assert ok is True
    assert session.calls[0][0] == "https://discord.com/api/v10/users/@me/channels"
    assert '"recipient_id": "1510522333142712322"' in session.calls[0][2]["payload_json"]
    assert session.calls[1][0] == "https://discord.com/api/v10/channels/dm-channel/messages"


def test_openclaw_message_adapter_pushes_qr_with_cli_media(tmp_path):
    image = tmp_path / "qr.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    calls = []

    def fake_runner(args, **kwargs):
        calls.append((args, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": '{"status":"ok"}', "stderr": ""})()

    adapter = OpenClawMessageAdapter(
        channel="openclaw-weixin",
        account="weixin-account",
        command="openclaw",
        runner=fake_runner,
    )

    ok = adapter.push_qr(image, "扫码恢复 wewe-rss", "wx-target@im.wechat")

    assert ok is True
    args, kwargs = calls[0]
    assert args == [
        "openclaw",
        "message",
        "send",
        "--channel",
        "openclaw-weixin",
        "--account",
        "weixin-account",
        "--target",
        "wx-target@im.wechat",
        "--message",
        "扫码恢复 wewe-rss",
        "--media",
        str(image),
        "--json",
    ]
    assert kwargs["timeout"] == 30


def test_openclaw_message_adapter_pushes_text_with_cli_message():
    calls = []

    def fake_runner(args, **kwargs):
        calls.append((args, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": '{"status":"ok"}', "stderr": ""})()

    adapter = OpenClawMessageAdapter(
        channel="openclaw-weixin",
        account="weixin-account",
        command="openclaw",
        runner=fake_runner,
    )

    ok = adapter.push_text("扫码已确认,wewe-rss token 已恢复", "wx-target@im.wechat")

    assert ok is True
    args, kwargs = calls[0]
    assert args == [
        "openclaw",
        "message",
        "send",
        "--channel",
        "openclaw-weixin",
        "--account",
        "weixin-account",
        "--target",
        "wx-target@im.wechat",
        "--message",
        "扫码已确认,wewe-rss token 已恢复",
        "--json",
    ]
    assert kwargs["timeout"] == 30
