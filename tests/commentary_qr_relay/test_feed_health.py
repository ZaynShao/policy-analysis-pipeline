from scripts.l1_collect.commentary_ingest.qr_relay.feed_health import feed_token_status


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {"content-type": "application/atom+xml"}
        self.content = b"<feed/>"


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        return self.responses.pop(0)


def test_feed_token_status_uses_bearer_auth_and_accepts_200():
    session = FakeSession([FakeResponse(200)])

    status = feed_token_status("http://localhost:4000", "auth-code", session=session)

    assert status.valid is True
    assert "feed health ok" in status.detail
    assert session.calls == [
        (
            "http://localhost:4000/feeds/all.atom",
            {"Authorization": "Bearer auth-code"},
            10,
        )
    ]


def test_feed_token_status_invalid_when_all_paths_fail():
    session = FakeSession([FakeResponse(401), FakeResponse(403)])

    status = feed_token_status(
        "http://localhost:4000",
        "auth-code",
        paths=("/feeds/all.atom", "/feeds/all.rss"),
        session=session,
    )

    assert status.valid is False
    assert "401" in status.detail
    assert "403" in status.detail
