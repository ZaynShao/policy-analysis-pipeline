"""Step 4.5 抽取后二次拦截:非政策标题在抽正文后仍被 quarantine(市监 backfill 最后防线)。

run_pipeline(批量 backfill 路径)不过 policy_gate,Step 3/Step 4.5 的 news_filter 是唯一防线。
市监 gov 域 issuer 抽不到(只命中 issuer_unknown_but_gov_domain),旧 Step 4.5 一律放行。
"""
from __future__ import annotations
import json
from pathlib import Path

from scripts.l1_collect.step4_5_extract import extract_all


def _write_fetch(in_dir: Path, name: str, url: str, title: str, body: str) -> None:
    in_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / name).write_text(json.dumps({
        "url": url, "title": title, "body": body,
        "city": "海南省", "city_code": "460000", "province": "海南省",
        "channel_type": "市监",
    }, ensure_ascii=False), encoding="utf-8")


def test_procurement_dropped_at_extract(tmp_path: Path):
    """采购中标公告(市监 gov 域,issuer 抽不到)旧逻辑入库;现应 quarantine。"""
    in_dir = tmp_path / "fetch"
    out_dir = tmp_path / "ext"
    quar = tmp_path / "quar.jsonl"
    _write_fetch(in_dir, "a.json",
                 "https://amr.hainan.gov.cn/x.html",
                 "海南省市场监督管理局采购项目中标公告",
                 "一、项目名称:xxx 二、中标供应商:yyy")
    extracted, quarantined = extract_all(in_dir, out_dir, quar)
    assert extracted == 0
    assert quarantined == 1


def test_real_policy_survives_extract(tmp_path: Path):
    """精度护栏:真政策(政府域名 issuer 抽不到)仍正常抽取入库。"""
    in_dir = tmp_path / "fetch"
    out_dir = tmp_path / "ext"
    quar = tmp_path / "quar.jsonl"
    _write_fetch(in_dir, "b.json",
                 "https://amr.hainan.gov.cn/zcfg/x.html",
                 "海南省市场监督管理局关于规范公平竞争审查工作的通知",
                 "根据有关规定,现将事项通知如下:……")
    extracted, quarantined = extract_all(in_dir, out_dir, quar)
    assert extracted == 1
    assert quarantined == 0
