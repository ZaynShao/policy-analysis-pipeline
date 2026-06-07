from scripts.l1_collect.commentary_ingest.filters import classify
from scripts.l1_collect.commentary_ingest.models import Disposition, FeedItem


def _item(title):
    return FeedItem(id="a" * 22, url="u", title=title, content_html="x",
                    date_published="2026-04-28", source_account="某号")


def test_recruitment_is_skipped():
    assert classify(_item("诚聘英才|2026校园招聘启动")).disposition == Disposition.SKIP_JUNK


def test_holiday_greeting_is_skipped():
    assert classify(_item("端午节快乐，放假通知")).disposition == Disposition.SKIP_JUNK


def test_pure_video_is_skipped():
    assert classify(_item("视频：花香柳马焕新城市生态")).disposition == Disposition.SKIP_JUNK


def test_procurement_with_capacity_is_market_intel():
    c = classify(_item("0.71元Wh，河北200MW800MWh储能项目EPC中标公示"))
    assert c.disposition == Disposition.MARKET_INTEL


def test_bidding_announcement_is_market_intel():
    assert classify(_item("浙江温州工商储设备招标公告")).disposition == Disposition.MARKET_INTEL


def test_ipo_financing_is_market_intel():
    assert classify(_item("晶科科技完成近2亿元融资")).disposition == Disposition.MARKET_INTEL


def test_normal_commentary_is_ingested():
    c = classify(_item("IIGF观点 | 可持续信息披露规则趋同下的制度比较与中国路径"))
    assert c.disposition == Disposition.INGEST
    assert c.reasons == []


def test_policy_interpretation_is_ingested():
    assert classify(_item("解读丨2025年两新政策如何加力扩围")).disposition == Disposition.INGEST
