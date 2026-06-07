"""检测 wewe-rss 微信 token 是否失效 + 告警。

判据:读 sqlite accounts.status(1=有效, 0=失效)。任一账号失效即需重新扫码。
告警通道:ALERT_WEBHOOK_URL(POST json)优先,无则仅记日志返回。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class TokenStatus:
    valid: bool
    account_name: str = ""
    detail: str = ""


def check_token(db_path: Path) -> TokenStatus:
    db_path = Path(db_path)
    if not db_path.exists():
        return TokenStatus(False, "", f"无法读取 wewe-rss DB: {db_path}")
    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = con.execute("SELECT name, status FROM accounts").fetchall()
    except sqlite3.Error as e:
        return TokenStatus(False, "", f"无法读取 accounts: {e}")
    finally:
        if con is not None:
            con.close()
    if not rows:
        return TokenStatus(False, "", "accounts 表为空,未登录")
    invalid = [name for name, status in rows if status != 1]
    if invalid:
        return TokenStatus(False, invalid[0],
                           f"{len(invalid)} 个账号 token 失效,需重新扫码")
    return TokenStatus(True, rows[0][0], "token 有效")


def alert(message: str, webhook_url: str = "") -> bool:
    """发告警。有 webhook 则 POST,返回是否送达;无则返回 False(调用方记日志)。"""
    if not webhook_url:
        return False
    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=15)
        return resp.ok
    except Exception:
        return False
