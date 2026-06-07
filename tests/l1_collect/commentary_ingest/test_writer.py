from pathlib import Path

import yaml

from scripts.l1_collect.commentary_ingest.models import FeedItem
from scripts.l1_collect.commentary_ingest.writer import (
    sanitize_filename, stage_market_intel, write_commentary,
)


def _item(title="测试评论标题"):
    return FeedItem(id="b" * 22,
                    url="https://mp.weixin.qq.com/s/" + "b" * 22,
                    title=title, content_html="x",
                    date_published="2026-04-28", source_account="某能源号")


def _read_fm(path: Path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm_text = text.split("---\n", 2)[1]
    return yaml.safe_load(fm_text), text


def test_write_commentary_creates_schema_compliant_file(tmp_path):
    path = write_commentary(_item(), "正文内容若干。", tmp_path)
    assert path.exists()
    fm, text = _read_fm(path)
    assert fm["title"] == "测试评论标题"
    assert fm["source_account"] == "某能源号"
    assert fm["source_url"].endswith("b" * 22)
    assert fm["date_published"] == "2026-04-28"
    assert fm["source"] == "wewe-rss"
    assert "fetched_at" in fm
    # L1 纪律:不写 LLM 判定字段
    assert "commentary_type" not in fm
    assert "business_tag" not in fm
    assert "related_policy" not in fm
    # 正文带标题
    assert "# 测试评论标题" in text
    assert "正文内容若干。" in text


def test_write_commentary_only_required_field_is_title(tmp_path):
    # schema commentary 仅 title 必填;其余字段都在白名单内
    allowed = {"title", "source_account", "source_url", "date_published",
               "fetched_at", "source"}
    fm, _ = _read_fm(write_commentary(_item(), "正文。", tmp_path))
    assert set(fm.keys()) <= allowed
    assert "title" in fm


def test_write_commentary_collision_appends_suffix(tmp_path):
    p1 = write_commentary(_item("同名"), "正文一。", tmp_path)
    p2 = write_commentary(_item("同名"), "正文二。", tmp_path)
    assert p1 != p2
    assert p2.stem.endswith("__1")


def test_sanitize_filename_replaces_illegal_chars():
    assert "/" not in sanitize_filename("a/b:c?d")
    assert sanitize_filename("   ") == "untitled"


def test_stage_market_intel_writes_json_not_vault(tmp_path):
    path = stage_market_intel(_item("河北200MW储能中标公示"), "正文。",
                              tmp_path, "2026-04-28", ["采购招标+容量"])
    assert path.suffix == ".json"
    assert "market_intel_staging" in str(path)
    assert "2026-04-28" in str(path)
    import json
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["id"] == "b" * 22
    assert rec["reasons"] == ["采购招标+容量"]
