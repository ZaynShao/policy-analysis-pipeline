from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .detector import token_needs_relay


RELAY_COMMAND = [sys.executable, "-m", "scripts.l1_collect.commentary_ingest.qr_relay.run"]


def resend_wewe_qr(
    db_path: str | Path,
    *,
    detector: Callable[[Path], Any] = token_needs_relay,
    spawn: Callable[[], Any] | None = None,
) -> dict[str, object]:
    """Check token status; if invalid, start the existing QR relay in background."""
    status = detector(Path(db_path))
    if status.valid:
        return {"action": "noop", "valid": True, "message": "token 仍有效,无需重发"}

    (spawn or _spawn_relay)()
    return {
        "action": "resent",
        "valid": False,
        "message": "已重新推送二维码,请扫描;扫码成功会收到确认",
    }


def _spawn_relay(
    *,
    popen: Callable[..., Any] = subprocess.Popen,
) -> Any:
    log_target = os.environ.get("QR_RELAY_LOG", "/var/log/policy-pipeline/qr_relay.log")
    try:
        log_handle = open(log_target, "ab")
    except OSError:
        log_handle = subprocess.DEVNULL

    return popen(
        RELAY_COMMAND,
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
        env=os.environ,
    )
