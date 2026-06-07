import sqlite3
from pathlib import Path

from scripts.l1_collect.commentary_ingest.token_health import check_token


def _make_db(tmp_path: Path, status: int) -> Path:
    db = tmp_path / "wewe-rss.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE accounts (id TEXT, name TEXT, status INTEGER, "
                "token TEXT, updated_at TEXT)")
    con.execute("INSERT INTO accounts VALUES ('1','邵子渊',?,'tok','2026-04-29')",
                (status,))
    con.commit()
    con.close()
    return db


def test_check_token_valid_when_status_1(tmp_path):
    st = check_token(_make_db(tmp_path, 1))
    assert st.valid is True


def test_check_token_invalid_when_status_0(tmp_path):
    st = check_token(_make_db(tmp_path, 0))
    assert st.valid is False
    assert st.account_name == "邵子渊"


def test_check_token_invalid_when_db_missing(tmp_path):
    st = check_token(tmp_path / "nope.db")
    assert st.valid is False
    assert "无法读取" in st.detail
