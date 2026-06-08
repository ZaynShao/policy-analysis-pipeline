"""Tests for step3_filter orchestrator."""
from __future__ import annotations
import json
from pathlib import Path

from scripts.l1_collect.step3_filter import filter_scan_rows
from scripts.l1_collect.dedup import DedupIndex


def test_filter_drops_news_and_dup(tmp_path: Path):
    scan_jsonl = tmp_path / "in.jsonl"
    rows = [
        # 政府域名 + 政策标题,issuer=None 但 gov 域 → 放行(Step 4.5 二次过滤)
        {"title": "关于xx的通知", "url": "https://www.gov.cn/zhengce/a.html",
         "date_hint": "2025-01-01", "source_channel": "www.gov.cn",
         "city": "国家", "city_code": "000000", "province": "",
         "channel_type": "政府网", "scanned_at": ""},
        # _市县 标题 → 被规则过滤
        {"title": "信阳新能源_市县", "url": "https://xinyang.gov.cn/news/x.html",
         "date_hint": "", "source_channel": "xinyang.gov.cn",
         "city": "信阳市", "city_code": "411500", "province": "河南省",
         "channel_type": "政府网", "scanned_at": ""},
        # 与第一条 URL 重复(tracking 参数不影响身份)→ 被查重
        {"title": "重复的通知", "url": "https://www.gov.cn/zhengce/a.html?utm_source=wx",
         "date_hint": "", "source_channel": "www.gov.cn",
         "city": "国家", "city_code": "000000", "province": "",
         "channel_type": "政府网", "scanned_at": ""},
    ]
    scan_jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )
    out = tmp_path / "out.jsonl"
    quar = tmp_path / "quar.jsonl"
    kept, dropped = filter_scan_rows(scan_jsonl, out, quar, dedup_idx=DedupIndex())
    assert kept == 1
    assert dropped == 2
    # 验证 quarantine 包含 drop_reasons
    quar_lines = [json.loads(l) for l in quar.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert all("drop_reasons" in x for x in quar_lines)


# ---------------------------------------------------------------------------
# U+0085 (NEL) over-split regression tests
# Same class of bug fixed in step4_fetch.py (commit 2008add).
# splitlines() splits on U+0085/U+2028/U+2029; split("\n") does not.
# ---------------------------------------------------------------------------

def _make_nel_row(title: str, url: str, **extra) -> str:
    """Serialize a candidate row with ensure_ascii=False so U+0085 is written raw."""
    row = {
        "title": title,
        "url": url,
        "date_hint": "2025-01-01",
        "source_channel": url.split("/")[2] if "//" in url else "",
        "city": "国家",
        "city_code": "000000",
        "province": "",
        "channel_type": "政府网",
        "scanned_at": "",
        **extra,
    }
    return json.dumps(row, ensure_ascii=False)


def test_nel_title_kept_path(tmp_path: Path):
    """U+0085 in title, gov-domain candidate → must be KEPT as one row (no crash)."""
    nel_title = "关于新能源\x85汽车补贴的通知"  # U+0085 embedded mid-title
    scan_jsonl = tmp_path / "in.jsonl"
    scan_jsonl.write_text(
        _make_nel_row(nel_title, "https://www.gov.cn/zhengce/nel.html"),
        encoding="utf-8",
    )
    out = tmp_path / "out.jsonl"
    quar = tmp_path / "quar.jsonl"

    kept, dropped = filter_scan_rows(scan_jsonl, out, quar, dedup_idx=DedupIndex())

    assert kept == 1, f"expected 1 kept, got {kept}"
    assert dropped == 0

    out_lines = [l for l in out.read_text(encoding="utf-8").split("\n") if l.strip()]
    assert len(out_lines) == 1, f"expected 1 line in out_jsonl, got {len(out_lines)}"
    parsed = json.loads(out_lines[0])
    assert parsed["title"] == nel_title, "title with U+0085 must survive intact"


def test_nel_title_quarantine_path(tmp_path: Path):
    """U+0085 in title, news/non-gov title → must be QUARANTINED as one row (no crash)."""
    # Use a title that triggers is_news_or_press (contains news keywords or non-gov domain)
    nel_title = "新闻稿\x85发布：xx公司签约仪式圆满成功"
    scan_jsonl = tmp_path / "in.jsonl"
    # Non-gov domain ensures it's filtered
    scan_jsonl.write_text(
        _make_nel_row(nel_title, "https://news.sina.com.cn/xx/nel.html"),
        encoding="utf-8",
    )
    out = tmp_path / "out.jsonl"
    quar = tmp_path / "quar.jsonl"

    kept, dropped = filter_scan_rows(scan_jsonl, out, quar, dedup_idx=DedupIndex())

    assert dropped == 1, f"expected 1 dropped, got {dropped}"
    assert kept == 0

    quar_lines = [l for l in quar.read_text(encoding="utf-8").split("\n") if l.strip()]
    assert len(quar_lines) == 1, f"expected 1 line in quarantine_jsonl, got {len(quar_lines)}"
    parsed = json.loads(quar_lines[0])
    assert parsed["title"] == nel_title, "title with U+0085 must survive intact in quarantine"
    assert "drop_reasons" in parsed
