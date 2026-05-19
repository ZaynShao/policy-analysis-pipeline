"""Step 3: 标题过滤 + 新闻稿过滤 + 三维查重 编排。

注意:此时 issuer 还没抽出来(那是 Step 4.5),所以 news_filter 只用 url + title 维度,
issuer=None 时:
  - 政府域名 → 放行(reasons 只含 issuer_unknown_but_gov_domain,Step 4.5 再判)
  - 非政府域名 → 过滤(进 quarantine)
"""
from __future__ import annotations
import json
from pathlib import Path

from .news_filter import is_news_or_press
from .dedup import DedupIndex


def filter_scan_rows(
    in_jsonl: Path, out_jsonl: Path, quarantine_jsonl: Path,
    dedup_idx: DedupIndex,
) -> tuple:
    """返回 (kept, dropped)。"""
    kept = 0
    dropped = 0
    out_lines: list = []
    quar_lines: list = []
    for line in in_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        title = row.get("title", "")
        url = row.get("url", "")
        f = is_news_or_press(url=url, title=title, issuer=None)
        # 区分 issuer_unknown_but_gov_domain(放行,Step 4.5 二次判)与真过滤
        relevant = [r for r in f.reasons if r != "issuer_unknown_but_gov_domain"]
        if relevant:
            quar_lines.append(json.dumps(
                {**row, "drop_reasons": relevant}, ensure_ascii=False,
            ))
            dropped += 1
            continue
        if dedup_idx.is_dup(url=url, official_number="", title=title):
            quar_lines.append(json.dumps(
                {**row, "drop_reasons": ["dup"]}, ensure_ascii=False,
            ))
            dropped += 1
            continue
        dedup_idx.add(url=url, official_number="", title=title)
        out_lines.append(line)
        kept += 1
    out_jsonl.write_text("\n".join(out_lines), encoding="utf-8")
    quarantine_jsonl.write_text("\n".join(quar_lines), encoding="utf-8")
    return kept, dropped
