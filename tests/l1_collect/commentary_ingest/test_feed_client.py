import json
from pathlib import Path

from scripts.l1_collect.commentary_ingest.feed_client import parse_feed

FIXTURE = Path(__file__).parent / "fixtures" / "feed_sample.json"


def test_parse_feed_returns_feeditems_from_real_fixture():
    items = parse_feed(FIXTURE.read_text(encoding="utf-8"))
    assert len(items) >= 1
    first = items[0]
    assert len(first.id) == 22
    assert first.url == f"https://mp.weixin.qq.com/s/{first.id}"
    assert first.title
    assert first.source_account


def test_parse_feed_normalizes_date_to_yyyy_mm_dd():
    raw = json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "items": [{
            "id": "tQnDiszHVcjKkO8nv2JulA",
            "url": "https://mp.weixin.qq.com/s/tQnDiszHVcjKkO8nv2JulA",
            "title": "绿色金融日报4.28",
            "content_html": "<p>正文</p>",
            "date_published": "2026-04-28T13:13:41+08:00",
            "authors": [{"name": "中央财经大学绿色金融国际研究院"}],
        }],
    })
    items = parse_feed(raw)
    assert items[0].date_published == "2026-04-28"
    assert items[0].source_account == "中央财经大学绿色金融国际研究院"


def test_parse_feed_uses_date_modified_and_singular_author():
    # 实测真实 wewe-rss:item 用 date_modified(非 date_published)+ author(单数)
    raw = json.dumps({
        "version": "https://jsonfeed.org/version/1",
        "items": [{
            "id": "X2_e2xd80ss6__rERIg4wQ",
            "url": "https://mp.weixin.qq.com/s/X2_e2xd80ss6__rERIg4wQ",
            "title": "综研观察｜美国创投行业",
            "content_html": "<p>正文</p>",
            "date_modified": "2026-04-29T11:14:55+08:00",
            "author": {"name": "综合开发研究院"},
        }],
    })
    items = parse_feed(raw)
    assert items[0].date_published == "2026-04-29"
    assert items[0].source_account == "综合开发研究院"
    assert items[0].id == "X2_e2xd80ss6__rERIg4wQ"


def test_parse_feed_empty_items_returns_empty_list():
    assert parse_feed('{"version":"x","items":[]}') == []
