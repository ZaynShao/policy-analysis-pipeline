from __future__ import annotations

from typing import Any, Iterable

import requests

from .detector import TokenStatus


DEFAULT_FEED_PATHS = ("/feeds/all.atom",)


def feed_token_status(
    base_url: str,
    auth_code: str,
    *,
    paths: Iterable[str] = DEFAULT_FEED_PATHS,
    session: Any | None = None,
    timeout: int = 10,
) -> TokenStatus:
    base = base_url.rstrip("/")
    http = session if session is not None else requests.Session()
    failures: list[str] = []
    for path in paths:
        try:
            resp = http.get(
                f"{base}{path}",
                headers={"Authorization": f"Bearer {auth_code}"},
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            failures.append(f"{path}: {type(exc).__name__}")
            continue
        if resp.status_code == 200:
            return TokenStatus(True, "", f"feed health ok: {path} HTTP 200")
        failures.append(f"{path}: HTTP {resp.status_code}")
    return TokenStatus(False, "", "feed health failed: " + "; ".join(failures))
