from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .detector import TokenStatus
from .feed_health import feed_token_status
from .qr_render import render_qr_png
from .run import QRRelayConfig, RelayResult, relay_once
from .wewe_login import WeweLoginClient

CST = timezone(timedelta(hours=8))


def _load_outage(qr_dir: Path) -> dict | None:
    path = Path(qr_dir) / "relay_outage.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "first_down_at" not in data or "count" not in data:
            return None
        return data
    except Exception:
        return None


def _save_outage(qr_dir: Path, first_down_at_iso: str, count: int) -> None:
    Path(qr_dir).mkdir(parents=True, exist_ok=True)
    (Path(qr_dir) / "relay_outage.json").write_text(
        json.dumps({"first_down_at": first_down_at_iso, "count": count}, ensure_ascii=False),
        encoding="utf-8",
    )


def _clear_outage(qr_dir: Path) -> None:
    path = Path(qr_dir) / "relay_outage.json"
    if path.exists():
        path.unlink()


def run_daily_check(
    *,
    db_path: Path,
    qr_dir: Path,
    target: str,
    wewe_base_url: str,
    auth_code: str,
    alert_webhook: str = "",
    poll_timeout_seconds: int = 300,
    poll_interval_seconds: int = 5,
    confirm_checks: int = 3,
    confirm_interval_seconds: int = 10,
    feed_checker: Callable[[str, str], TokenStatus] = feed_token_status,
    relay: Any = relay_once,
    login_client: Any | None = None,
    adapter: Any | None = None,
    qr_renderer: Any = render_qr_png,
    sleeper: Any | None = None,
    now: datetime | None = None,
) -> RelayResult:
    now = now or datetime.now(CST)
    status = feed_checker(wewe_base_url, auth_code)
    if status.valid:
        _clear_outage(qr_dir)
        return RelayResult(True, False, True, status.detail)

    prev = _load_outage(qr_dir)
    first_down = datetime.fromisoformat(prev["first_down_at"]) if prev else now
    count = (prev["count"] if prev else 0) + 1
    _save_outage(qr_dir, first_down.isoformat(), count)
    hours = int((now - first_down).total_seconds() // 3600)
    note = f"第 {count} 次提醒 · token 自 {first_down.strftime('%m-%d %H:%M')} 起失效(约 {hours}h)"

    config = QRRelayConfig(
        db_path=Path(db_path),
        qr_dir=Path(qr_dir),
        target=target,
        wewe_base_url=wewe_base_url,
        auth_code=auth_code,
        alert_webhook=alert_webhook,
        poll_timeout_seconds=poll_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        confirm_checks=confirm_checks,
        confirm_interval_seconds=confirm_interval_seconds,
        note=note,
    )

    def detector(_db_path: Path) -> TokenStatus:
        return feed_checker(wewe_base_url, auth_code)

    kwargs: dict[str, Any] = {
        "detector": detector,
        "login_client": login_client if login_client is not None else WeweLoginClient(
            wewe_base_url,
            auth_code,
        ),
        "adapter": adapter,
        "qr_renderer": qr_renderer,
    }
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    result = relay(config, **kwargs)
    if result.restored:
        _clear_outage(qr_dir)
    return result


def config_from_env(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Daily wewe-rss feed health check with QR relay")
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
    return args


def main(argv: list[str] | None = None) -> int:
    args = config_from_env(argv)
    result = run_daily_check(
        db_path=Path(args.db_path).expanduser(),
        qr_dir=Path(args.qr_dir),
        target=args.target,
        wewe_base_url=args.wewe_base_url,
        auth_code=args.auth_code,
        alert_webhook=args.alert_webhook,
        poll_timeout_seconds=args.poll_timeout,
        poll_interval_seconds=args.poll_interval,
    )
    print(json.dumps({
        "checked": result.checked,
        "relayed": result.relayed,
        "restored": result.restored,
        "detail": result.detail,
        "qr_path": str(result.qr_path) if result.qr_path else "",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False))
    return 0 if result.restored else 1


if __name__ == "__main__":
    raise SystemExit(main())
