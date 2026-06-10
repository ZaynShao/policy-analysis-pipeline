"""统一告警:openclaw→飞书文字。绝不 raise(告警通道不得弄死主流程)。

env:OPENCLAW_CHANNEL / OPENCLAW_ACCOUNT / OPENCLAW_IM_TARGET / OPENCLAW_COMMAND
CLI:python3 -m scripts.service.notify "消息"(cron `|| notify` 用,恒 exit 0)
"""
from __future__ import annotations

import os
import sys
from typing import Any


def send_text(message: str, *, adapter: Any | None = None) -> bool:
    """推文字到飞书目标。绝不 raise。"""
    target = os.environ.get("OPENCLAW_IM_TARGET", "")
    try:
        if adapter is None:
            channel = os.environ.get("OPENCLAW_CHANNEL", "")
            if not channel or not target:
                return False
            from scripts.l1_collect.commentary_ingest.qr_relay.openclaw import (
                OpenClawMessageAdapter,
            )

            adapter = OpenClawMessageAdapter(
                channel=channel,
                account=os.environ.get("OPENCLAW_ACCOUNT", ""),
                command=os.environ.get("OPENCLAW_COMMAND", "openclaw"),
            )
        if not target:
            return False
        return bool(adapter.push_text(message, target))
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    """CLI 入口:python3 -m scripts.service.notify "消息"(cron 用,恒 exit 0)"""
    args = argv if argv is not None else sys.argv[1:]
    msg = " ".join(args) or "[policy-pipeline] (空告警)"
    sent = send_text(msg)
    print(f"notify sent={sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
