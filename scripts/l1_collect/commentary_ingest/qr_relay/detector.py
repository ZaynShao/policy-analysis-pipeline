from __future__ import annotations

import importlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TokenStatus:
    valid: bool
    account_name: str = ""
    detail: str = ""


def _load_token_health() -> Any | None:
    try:
        return importlib.import_module("scripts.l1_collect.commentary_ingest.token_health")
    except ModuleNotFoundError:
        return None


def _fallback_check_token(db_path: Path) -> TokenStatus:
    db_path = Path(db_path)
    if not db_path.exists():
        return TokenStatus(False, "", f"无法读取 wewe-rss DB: {db_path}")
    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = con.execute("SELECT name, status FROM accounts").fetchall()
    except sqlite3.Error as exc:
        return TokenStatus(False, "", f"无法读取 accounts: {exc}")
    finally:
        if con is not None:
            con.close()
    if not rows:
        return TokenStatus(False, "", "accounts 表为空,未登录")
    valid = [name for name, status in rows if status == 1]
    if valid:
        return TokenStatus(True, valid[0], f"至少 1 个账号 token 有效 ({len(valid)}/{len(rows)})")
    return TokenStatus(False, rows[0][0], f"{len(rows)} 个账号 token 均失效,需重新扫码")


def token_needs_relay(db_path: Path, token_health: Any | None = None) -> TokenStatus:
    """Return the current wewe-rss token status via the existing health seam.

    The fallback exists only because this branch is additive and the live
    commentary_ingest seam is currently in a sibling worktree.
    """
    health = token_health if token_health is not None else _load_token_health()
    if health is not None:
        st = health.check_token(Path(db_path))
        return TokenStatus(bool(st.valid), getattr(st, "account_name", ""), getattr(st, "detail", ""))
    return _fallback_check_token(Path(db_path))


def fallback_alert(message: str, webhook_url: str = "", token_health: Any | None = None) -> bool:
    health = token_health if token_health is not None else _load_token_health()
    if health is None or not hasattr(health, "alert"):
        return False
    return bool(health.alert(message, webhook_url))
