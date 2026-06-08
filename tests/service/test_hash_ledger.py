from pathlib import Path
from scripts.service.hash_ledger import (
    LedgerEntry, compute_hash, load_ledger, save_ledger, needs_rebuild, mark_done,
)

def test_compute_hash_stable():
    assert compute_hash("内容A") == compute_hash("内容A")
    assert compute_hash("内容A") != compute_hash("内容B")

def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "ledger.json"
    entries = {"P_2024_NDRC_718": LedgerEntry("P_2024_NDRC_718", "abc", 1)}
    save_ledger(p, entries)
    loaded = load_ledger(p)
    assert loaded["P_2024_NDRC_718"].raw_content_hash == "abc"
    assert loaded["P_2024_NDRC_718"].pipeline_version == 1

def test_load_missing_returns_empty(tmp_path):
    assert load_ledger(tmp_path / "nope.json") == {}

def test_needs_rebuild_new_pid(tmp_path):
    assert needs_rebuild("P_NEW", "txt", 1, {}) is True

def test_needs_rebuild_hash_changed():
    led = {"P_X": LedgerEntry("P_X", compute_hash("old"), 1)}
    assert needs_rebuild("P_X", "new", 1, led) is True

def test_needs_rebuild_version_bumped():
    led = {"P_X": LedgerEntry("P_X", compute_hash("same"), 1)}
    assert needs_rebuild("P_X", "same", 2, led) is True

def test_needs_rebuild_unchanged():
    led = {"P_X": LedgerEntry("P_X", compute_hash("same"), 1)}
    assert needs_rebuild("P_X", "same", 1, led) is False

def test_mark_done_updates_entry():
    led = {}
    mark_done(led, "P_X", "txt", 3)
    assert led["P_X"].pipeline_version == 3
    assert led["P_X"].raw_content_hash == compute_hash("txt")
