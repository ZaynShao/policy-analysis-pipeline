from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .detector import TokenStatus, fallback_alert, token_needs_relay
from .openclaw import DiscordBotAdapter, OpenClawMessageAdapter, OpenClawNotifyFallback
from .qr_render import render_qr_png
from .wewe_login import WeweLoginClient


@dataclass(frozen=True)
class QRRelayConfig:
    db_path: Path
    qr_dir: Path
    target: str
    wewe_base_url: str = "http://localhost:4000"
    auth_code: str = ""
    alert_webhook: str = ""
    poll_timeout_seconds: int = 300
    poll_interval_seconds: int = 5
    confirm_checks: int = 1
    confirm_interval_seconds: int = 3
    note: str = ""


@dataclass(frozen=True)
class RelayResult:
    checked: bool
    relayed: bool
    restored: bool
    detail: str
    qr_path: Path | None = None


def relay_once(
    config: QRRelayConfig,
    *,
    detector: Callable[[Path], TokenStatus] = token_needs_relay,
    login_client: Any | None = None,
    adapter: Any | None = None,
    qr_renderer: Callable[[str, Path], Path] = render_qr_png,
    sleeper: Callable[[float], None] = time.sleep,
) -> RelayResult:
    status = detector(Path(config.db_path))
    if status.valid:
        return RelayResult(True, False, True, status.detail)

    client = login_client if login_client is not None else WeweLoginClient(
        config.wewe_base_url,
        config.auth_code,
    )
    login = client.create_login_url()
    qr_path = Path(config.qr_dir) / f"wewe-login-{login.uuid}.png"
    qr_renderer(login.scan_url, qr_path)

    caption = (
        "[policy-pipeline] 微信读书 token 失效,请用微信扫码恢复 wewe-rss 登录。"
        f"账号:{status.account_name or 'unknown'} uuid:{login.uuid}"
    )
    caption = caption + (f"\n{config.note}" if config.note else "")
    if not _push_qr(adapter, qr_path, caption, config.target):
        _fallback_notice(caption, config, qr_path)
        return RelayResult(True, False, False, "QR push failed; fallback alert sent", qr_path)

    try:
        client.poll_until_success(
            login.uuid,
            timeout_seconds=config.poll_timeout_seconds,
            interval_seconds=config.poll_interval_seconds,
            sleeper=sleeper,
        )
    except TimeoutError as exc:
        _push_text(adapter, "[policy-pipeline] 微信读书扫码超时,wewe-rss token 未恢复。", config.target)
        _fallback_notice(f"{caption}；扫码超时:{exc}", config, qr_path)
        return RelayResult(True, True, False, "login poll timed out", qr_path)

    restored = _confirm_token_restored(config, detector, sleeper)
    if restored:
        _push_text(adapter, "[policy-pipeline] 微信读书扫码已确认,wewe-rss token 已恢复。", config.target)
    else:
        _push_text(adapter, "[policy-pipeline] 微信读书扫码已确认,但 token 健康检查仍未恢复。", config.target)
    return RelayResult(True, True, restored, "token restored" if restored else "token still invalid", qr_path)


def _confirm_token_restored(
    config: QRRelayConfig,
    detector: Callable[[Path], TokenStatus],
    sleeper: Callable[[float], None],
) -> bool:
    for idx in range(max(config.confirm_checks, 1)):
        if detector(Path(config.db_path)).valid:
            return True
        if idx + 1 < config.confirm_checks:
            sleeper(config.confirm_interval_seconds)
    return False


def _push_qr(adapter: Any | None, qr_path: Path, caption: str, target: str) -> bool:
    try:
        push_adapter = adapter if adapter is not None else _adapter_from_env()
        return bool(push_adapter.push_qr(qr_path, caption, target))
    except Exception:
        return False


def _push_text(adapter: Any | None, message: str, target: str) -> bool:
    try:
        push_adapter = adapter if adapter is not None else _adapter_from_env()
        if hasattr(push_adapter, "push_text"):
            return bool(push_adapter.push_text(message, target))
    except Exception:
        return False
    return False


def _adapter_from_env() -> Any:
    channel = os.environ.get("OPENCLAW_CHANNEL") or os.environ.get("OPENCLAW_IM_CHANNEL")
    if channel:
        return OpenClawMessageAdapter(
            channel=channel,
            account=os.environ.get("OPENCLAW_ACCOUNT", ""),
            command=os.environ.get("OPENCLAW_COMMAND", "openclaw"),
        )

    token = os.environ.get("OPENCLAW_DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "OPENCLAW_CHANNEL or OPENCLAW_DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN is required"
        )
    return DiscordBotAdapter(token)


def _fallback_notice(caption: str, config: QRRelayConfig, qr_path: Path) -> None:
    message = f"{caption}；QR 已生成但未送达图片通道:{qr_path}"
    if fallback_alert(message, config.alert_webhook):
        return
    OpenClawNotifyFallback().notify(message)


def config_from_env(argv: list[str] | None = None) -> QRRelayConfig:
    ap = argparse.ArgumentParser(description="Relay wewe-rss login QR to OpenClaw IM")
    ap.add_argument("--db-path", default=os.environ.get("WEWE_DB_PATH", ""))
    ap.add_argument("--qr-dir", default=os.environ.get("WEWE_QR_DIR", "state/wewe_qr"))
    ap.add_argument("--target", default=os.environ.get("OPENCLAW_IM_TARGET", ""))
    ap.add_argument("--wewe-base-url", default=os.environ.get("WEWE_BASE_URL", "http://localhost:4000"))
    ap.add_argument("--auth-code", default=os.environ.get("WEWE_AUTH_CODE", ""))
    ap.add_argument("--alert-webhook", default=os.environ.get("ALERT_WEBHOOK_URL", ""))
    ap.add_argument("--poll-timeout", type=int, default=int(os.environ.get("WEWE_LOGIN_TIMEOUT", "300")))
    ap.add_argument("--poll-interval", type=int, default=int(os.environ.get("WEWE_LOGIN_INTERVAL", "5")))
    args = ap.parse_args(argv)
    if not args.db_path:
        ap.error("--db-path or WEWE_DB_PATH is required")
    if not args.target:
        ap.error("--target or OPENCLAW_IM_TARGET is required")
    if not args.auth_code:
        ap.error("--auth-code or WEWE_AUTH_CODE is required")
    return QRRelayConfig(
        db_path=Path(args.db_path).expanduser(),
        qr_dir=Path(args.qr_dir),
        target=args.target,
        wewe_base_url=args.wewe_base_url,
        auth_code=args.auth_code,
        alert_webhook=args.alert_webhook,
        poll_timeout_seconds=args.poll_timeout,
        poll_interval_seconds=args.poll_interval,
    )


def main(argv: list[str] | None = None) -> int:
    result = relay_once(config_from_env(argv))
    payload = {
        "checked": result.checked,
        "relayed": result.relayed,
        "restored": result.restored,
        "detail": result.detail,
        "qr_path": str(result.qr_path) if result.qr_path else "",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if result.restored else 1


if __name__ == "__main__":
    raise SystemExit(main())
