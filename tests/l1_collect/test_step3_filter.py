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
        # 与第一条 URL 重复 → 被查重
        {"title": "重复的通知", "url": "https://www.gov.cn/zhengce/a.html?dup=1",
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
