import json
from pathlib import Path

from scripts.l1_collect.commentary_ingest.models import FeedItem
from scripts.l1_collect.commentary_ingest.run import ingest_items


def _items():
    return [
        FeedItem("a" * 22, "https://mp.weixin.qq.com/s/" + "a" * 22,
                 "IIGF观点 | 制度比较与中国路径", "<p>" + "正文。" * 80 + "</p>",
                 "2026-04-28", "中央财经大学绿色金融国际研究院"),
        FeedItem("b" * 22, "https://mp.weixin.qq.com/s/" + "b" * 22,
                 "河北200MW800MWh储能项目EPC中标公示", "<p>" + "行情。" * 80 + "</p>",
                 "2026-04-27", "储能与电力市场"),
        FeedItem("c" * 22, "https://mp.weixin.qq.com/s/" + "c" * 22,
                 "诚聘英才|2026校园招聘", "<p>" + "招聘。" * 80 + "</p>",
                 "2026-04-26", "某号"),
    ]


def test_ingest_items_routes_by_disposition(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    summary = ingest_items(_items(), vault_dir=vault, state_dir=state,
                           fetch_fallback=False)
    assert summary["ingested"] == 1
    assert summary["market_intel"] == 1
    assert summary["skipped_junk"] == 1
    # commentary 落了 1 篇
    assert len(list((vault / "0_raw" / "commentaries").glob("*.md"))) == 1
    # market_intel 暂存 1 条
    staged = list((state / "commentary_ingest" / "market_intel_staging").rglob("*.json"))
    assert len(staged) == 1


def test_ingest_items_idempotent_second_run_skips_all(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    ingest_items(_items(), vault_dir=vault, state_dir=state, fetch_fallback=False)
    summary2 = ingest_items(_items(), vault_dir=vault, state_dir=state,
                            fetch_fallback=False)
    assert summary2["duplicates"] == 3
    assert summary2["ingested"] == 0
    # 没多写文件
    assert len(list((vault / "0_raw" / "commentaries").glob("*.md"))) == 1


def test_transient_empty_not_recorded_so_retries_next_run(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    item = [FeedItem("d" * 22, "https://mp.weixin.qq.com/s/" + "d" * 22,
                     "正常标题无噪音", "", "2026-04-28", "某号")]
    s1 = ingest_items(item, vault_dir=vault, state_dir=state, fetch_fallback=False)
    assert s1["transient_fail"] == 1
    assert s1["ingested"] == 0
    # 未记台账 → 第二轮不是 duplicate,仍按 transient 重试(不被永久跳过)
    s2 = ingest_items(item, vault_dir=vault, state_dir=state, fetch_fallback=False)
    assert s2["duplicates"] == 0
    assert s2["transient_fail"] == 1


def test_deleted_recorded_so_skipped_next_run(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    item = [FeedItem("e" * 22, "https://mp.weixin.qq.com/s/" + "e" * 22,
                     "正常标题", "<p>该内容已被发布者删除</p>", "2026-04-28", "某号")]
    s1 = ingest_items(item, vault_dir=vault, state_dir=state, fetch_fallback=False)
    assert s1["unprocessable"] == 1
    # 真删除已记台账 → 第二轮判 duplicate,不再重试
    s2 = ingest_items(item, vault_dir=vault, state_dir=state, fetch_fallback=False)
    assert s2["duplicates"] == 1


def test_coverage_warning_when_no_overlap_with_history(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    first = [FeedItem("a" * 22, "https://mp.weixin.qq.com/s/" + "a" * 22,
                      "历史评论", "<p>" + "正文。" * 80 + "</p>", "2026-04-20", "某号")]
    ingest_items(first, vault_dir=vault, state_dir=state, fetch_fallback=False)
    # 第二轮全新 url、与历史零重叠 → 触发覆盖告警
    fresh = [FeedItem("z" * 22, "https://mp.weixin.qq.com/s/" + "z" * 22,
                      "新评论", "<p>" + "正文。" * 80 + "</p>", "2026-04-28", "某号")]
    s2 = ingest_items(fresh, vault_dir=vault, state_dir=state, fetch_fallback=False)
    assert "coverage_warning" in s2


def test_no_coverage_warning_on_first_run(tmp_path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    fresh = [FeedItem("a" * 22, "https://mp.weixin.qq.com/s/" + "a" * 22,
                      "首轮评论", "<p>" + "正文。" * 80 + "</p>", "2026-04-20", "某号")]
    s = ingest_items(fresh, vault_dir=vault, state_dir=state, fetch_fallback=False)
    assert "coverage_warning" not in s
