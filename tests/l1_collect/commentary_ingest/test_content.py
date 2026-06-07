from scripts.l1_collect.commentary_ingest.content import html_to_text, to_body
from scripts.l1_collect.commentary_ingest.models import FeedItem


def _item(content_html="", url="https://mp.weixin.qq.com/s/" + "a" * 22):
    return FeedItem(id="a" * 22, url=url, title="标题",
                    content_html=content_html, date_published="2026-04-28",
                    source_account="某号")


def test_html_to_text_strips_tags():
    text = html_to_text("<p>第一段</p><p>第二段</p>")
    assert "第一段" in text and "第二段" in text
    assert "<p>" not in text


def test_to_body_uses_feed_content_when_present():
    long_html = "<p>" + ("有效正文内容。" * 50) + "</p>"
    body, src = to_body(_item(content_html=long_html), fetch_fallback=False)
    assert "有效正文内容" in body
    assert src == "feed"


def test_to_body_marks_empty_when_no_content_and_no_fallback():
    body, src = to_body(_item(content_html=""), fetch_fallback=False)
    assert src == "empty"
    assert body == ""


def test_to_body_short_content_triggers_empty_without_fallback():
    body, src = to_body(_item(content_html="<p>短</p>"), fetch_fallback=False,
                        min_len=200)
    assert src == "empty"


def test_to_body_rejects_wechat_error_shell():
    # 反爬壳页:过 200 字但命中失败标记 → 判 empty(确定性,不靠 LLM)
    shell = "<p>" + "环境异常 当前环境异常，完成验证后即可继续访问。" * 8 + "</p>"
    body, src = to_body(_item(content_html=shell), fetch_fallback=False)
    assert src == "empty"


def test_is_low_quality_accepts_long_real_article():
    from scripts.l1_collect.commentary_ingest.content import is_low_quality
    real = "这是一篇正常的政策评论。" * 100
    assert is_low_quality(real) is False
