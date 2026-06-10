import pytest

from scripts.l1_collect.commentary_ingest.models import FeedItem
from scripts.l1_collect.commentary_ingest.run import filter_since, validate_since


def _item(date):
    return FeedItem(id="x" * 22, url=f"https://mp.weixin.qq.com/s/{date or 'nodate'}",
                    title="t", content_html="<p>b</p>", date_published=date,
                    source_account="acc")


def test_filter_since_drops_older_keeps_newer_and_undated():
    items = [_item("2026-06-05"), _item("2026-06-07"), _item("2026-06-09"), _item("")]
    kept = filter_since(items, "2026-06-07")
    assert [i.date_published for i in kept] == ["2026-06-07", "2026-06-09", ""]


def test_filter_since_empty_threshold_keeps_all():
    items = [_item("2026-06-05"), _item("")]
    assert filter_since(items, "") == items


def test_validate_since_accepts_iso_and_empty():
    assert validate_since("2026-06-07") == "2026-06-07"
    assert validate_since("") == ""


def test_validate_since_rejects_malformed():
    with pytest.raises(ValueError):
        validate_since("2026-6-7")
    with pytest.raises(ValueError):
        validate_since("2026/06/07")
