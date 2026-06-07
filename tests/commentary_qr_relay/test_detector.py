import sqlite3

from scripts.l1_collect.commentary_ingest.qr_relay.detector import token_needs_relay


def test_token_needs_relay_detects_invalid_account_from_temp_sqlite(tmp_path):
    db_path = tmp_path / "wewe-rss.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE accounts(name TEXT, status INTEGER)")
    con.execute("INSERT INTO accounts VALUES (?, ?)", ("微信读书", 0))
    con.commit()
    con.close()

    status = token_needs_relay(db_path)

    assert status.valid is False
    assert status.account_name == "微信读书"
    assert "token" in status.detail


def test_token_needs_relay_accepts_any_valid_account_from_history(tmp_path):
    db_path = tmp_path / "wewe-rss.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE accounts(name TEXT, status INTEGER)")
    con.execute("INSERT INTO accounts VALUES (?, ?)", ("旧账号", 0))
    con.execute("INSERT INTO accounts VALUES (?, ?)", ("当前账号", 1))
    con.commit()
    con.close()

    status = token_needs_relay(db_path)

    assert status.valid is True
    assert status.account_name == "当前账号"
    assert "至少 1 个账号 token 有效" in status.detail
