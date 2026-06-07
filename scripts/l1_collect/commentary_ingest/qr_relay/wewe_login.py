from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class LoginSession:
    uuid: str
    scan_url: str


class WeweLoginClient:
    def __init__(
        self,
        base_url: str,
        auth_code: str,
        *,
        session: Any | None = None,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_code = auth_code
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.auth_code}

    def create_login_url(self) -> LoginSession:
        resp = self.session.post(
            f"{self.base_url}/trpc/platform.createLoginUrl",
            headers=self._headers,
            json={},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = _trpc_data(resp.json())
        return LoginSession(uuid=data["uuid"], scan_url=data["scanUrl"])

    def get_login_result(self, uuid: str) -> dict[str, Any]:
        raw_input = json.dumps({"id": uuid}, separators=(",", ":"))
        resp = self.session.get(
            f"{self.base_url}/trpc/platform.getLoginResult?input={quote(raw_input)}",
            headers=self._headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return _trpc_data(resp.json())

    def poll_until_success(
        self,
        uuid: str,
        *,
        timeout_seconds: int = 300,
        interval_seconds: int = 5,
        sleeper: Any = time.sleep,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_result: dict[str, Any] = {}
        while time.monotonic() <= deadline:
            try:
                last_result = self.get_login_result(uuid)
            except requests.exceptions.Timeout:
                last_result = {"status": "pending_timeout"}
                sleeper(interval_seconds)
                continue
            except requests.exceptions.RequestException as exc:
                last_result = {"status": "pending_http_error", "error": str(exc)}
                sleeper(interval_seconds)
                continue
            if _looks_successful(last_result):
                return last_result
            sleeper(interval_seconds)
        raise TimeoutError(f"wewe-rss login timed out for uuid={uuid}; last={last_result}")


def _trpc_data(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        data = payload["result"]["data"]
    except KeyError as exc:
        raise ValueError(f"unexpected tRPC response shape: {payload}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"unexpected tRPC data shape: {payload}")
    return data


def _looks_successful(data: dict[str, Any]) -> bool:
    status = str(data.get("status", "")).lower()
    if status in {"confirmed", "success", "logged_in", "login_success"}:
        return True
    if data.get("token") or data.get("user") or data.get("account"):
        return True
    return bool(data.get("ok") is True or data.get("success") is True)
