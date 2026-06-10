from scripts.l1_collect.commentary_ingest.qr_relay.wewe_login import (
    LoginSession,
    WeweLoginClient,
)
import requests


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url, headers, json, timeout))
        return FakeResponse(
            {
                "result": {
                    "data": {
                        "uuid": "uuid-1",
                        "scanUrl": "https://open.weixin.qq.com/connect/confirm?uuid=uuid-1",
                    }
                }
            }
        )

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, headers, None, timeout))
        return FakeResponse({"result": {"data": {"status": "confirmed"}}})


def test_create_login_url_uses_bare_trpc_auth_and_empty_body():
    session = FakeSession()
    client = WeweLoginClient("http://localhost:4000", "secret-code", session=session)

    login = client.create_login_url()

    assert login == LoginSession(
        uuid="uuid-1",
        scan_url="https://open.weixin.qq.com/connect/confirm?uuid=uuid-1",
    )
    assert session.calls[0] == (
        "POST",
        "http://localhost:4000/trpc/platform.createLoginUrl",
        {"Authorization": "secret-code"},
        {},
        15,
    )


def test_get_login_result_encodes_uuid_as_trpc_input_json():
    session = FakeSession()
    client = WeweLoginClient("http://localhost:4000/", "secret-code", session=session)

    result = client.get_login_result("uuid-1")

    method, url, headers, _, timeout = session.calls[-1]
    assert method == "GET"
    assert url == (
        "http://localhost:4000/trpc/platform.getLoginResult"
        "?input=%7B%22id%22%3A%22uuid-1%22%7D"
    )
    assert headers == {"Authorization": "secret-code"}
    assert timeout == 15
    assert result == {"status": "confirmed"}


class TimeoutThenSuccessSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        if self.calls == 1:
            raise requests.exceptions.ReadTimeout("long poll pending")
        return FakeResponse({"result": {"data": {"status": "confirmed"}}})


def test_poll_until_success_treats_read_timeout_as_pending_scan():
    session = TimeoutThenSuccessSession()
    client = WeweLoginClient("http://localhost:4000", "secret-code", session=session)

    result = client.poll_until_success(
        "uuid-1",
        timeout_seconds=30,
        interval_seconds=0,
        sleeper=lambda _: None,
    )

    assert result == {"status": "confirmed"}
    assert session.calls == 2


class HttpErrorThenSuccessSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        if self.calls == 1:
            response = type("Response", (), {"status_code": 500, "text": "Login failed: 402"})()
            raise requests.exceptions.HTTPError("500 Server Error", response=response)
        return FakeResponse({"result": {"data": {"status": "confirmed"}}})


def test_poll_until_success_treats_http_error_as_pending_scan_failure():
    session = HttpErrorThenSuccessSession()
    client = WeweLoginClient("http://localhost:4000", "secret-code", session=session)

    result = client.poll_until_success(
        "uuid-1",
        timeout_seconds=30,
        interval_seconds=0,
        sleeper=lambda _: None,
    )

    assert result == {"status": "confirmed"}
    assert session.calls == 2


def test_add_account_posts_id_token_name_status_to_trpc_account_add():
    session = FakeSession()
    client = WeweLoginClient("http://localhost:4000", "secret-code", session=session)

    client.add_account(account_id="46732154", token="jwt-xyz", name="读书账号")

    method, url, headers, body, timeout = session.calls[-1]
    assert method == "POST"
    assert url == "http://localhost:4000/trpc/account.add"
    assert headers == {"Authorization": "secret-code"}
    assert body == {"id": "46732154", "token": "jwt-xyz", "name": "读书账号", "status": 1}
    assert timeout == 15
