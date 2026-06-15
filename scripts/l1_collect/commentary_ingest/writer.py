"""写 vault commentary md(仅追加)+ market_intel staging json。

frontmatter 确定性,只写 SCHEMA commentary 白名单内字段,不写 LLM 判定
(commentary_type/business_tag/related_policy 留给 L2)。
文件名规则对齐现有 vault(非法字符替换 + 截断 80 + 碰撞 __n)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .models import FeedItem

CST = timezone(timedelta(hours=8))


def sanitize_filename(title: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title)[:80]   # \x00-\x1f 覆盖 \n\r\t 及全部控制字符
    return t.strip() or "untitled"


def write_commentary(item: FeedItem, body: str, vault_dir: Path) -> Path:
    """写 {vault_dir}/0_raw/commentaries/{title}.md,返回路径。仅追加(不覆盖)。"""
    com_dir = Path(vault_dir) / "0_raw" / "commentaries"
    com_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": item.title,
        "source_account": item.source_account,
        "source_url": item.url,
        "date_published": item.date_published or None,
        "fetched_at": datetime.now(CST).isoformat(timespec="seconds"),
        "source": "wewe-rss",
    }
    base = sanitize_filename(item.title)
    fn = com_dir / f"{base}.md"
    n = 1
    while fn.exists():
        fn = com_dir / f"{base}__{n}.md"
        n += 1
    body_md = f"# {item.title}\n\n{body.strip()}\n"
    content = "---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + body_md
    fn.write_text(content, encoding="utf-8")
    return fn


def stage_market_intel(item: FeedItem, body: str, state_dir: Path,
                       run_date: str, reasons: list) -> Path:
    """market_intel 文章暂存 json(不入 vault),等 B1。"""
    out_dir = Path(state_dir) / "commentary_ingest" / "market_intel_staging" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "id": item.id,
        "url": item.url,
        "title": item.title,
        "source_account": item.source_account,
        "date_published": item.date_published,
        "body": body,
        "reasons": reasons,
        "staged_at": datetime.now(CST).isoformat(timespec="seconds"),
    }
    path = out_dir / f"{item.id}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
