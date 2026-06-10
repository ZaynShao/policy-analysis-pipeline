"""commentary_ingest 编排 CLI。

用法:
  python3 -m scripts.l1_collect.commentary_ingest.run \\
    --feed-url http://localhost:4000/feeds/all.json \\
    --auth-code "$WEWE_AUTH_CODE" \\
    --vault-dir "$VAULT_DIR" --state-dir state \\
    --db-path ~/wewe-rss-data/wewe-rss.db

  # 仅检查 token:
  python3 -m scripts.l1_collect.commentary_ingest.run --check-token \\
    --db-path ~/wewe-rss-data/wewe-rss.db

所有路径/凭据经 CLI/env 注入,零硬编码(可移植 spec §9)。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .content import to_body
from .feed_client import fetch_feed
from .filters import classify
from .ledger import load_seen_urls, record_dispositions, write_last_run
from .models import Disposition
from .token_health import alert, check_token
from .writer import stage_market_intel, write_commentary

CST = timezone(timedelta(hours=8))


def validate_since(since: str) -> str:
    """--since 格式校验:空串或严格 YYYY-MM-DD,否则 ValueError(防静默全丢)。"""
    if since:
        # 严格验证:YYYY-MM-DD 格式(年 4 位,月/日各 2 位)
        if not (len(since) == 10 and since[4] == '-' and since[7] == '-'):
            raise ValueError(f"--since 格式须为 YYYY-MM-DD(收到: {since!r})")
        datetime.strptime(since, "%Y-%m-%d")  # 验证日期有效性
    return since


def filter_since(items: list, since: str) -> list:
    """--since 下限:date 非空且 < since 的丢弃;date 为空保留(去重兜底)。"""
    if not since:
        return items
    return [i for i in items if not i.date_published or i.date_published >= since]


def ingest_items(items: list, *, vault_dir: Path, state_dir: Path,
                 fetch_fallback: bool = True) -> dict:
    """对一批 FeedItem 执行 去重→过滤→正文→写入→记账,返回 summary。

    真删除壳页(src=='deleted')记台账永久跳过;瞬时失败(src=='empty')不记台账,
    下轮可重试。有历史却与本轮 feed 零重叠 → coverage_warning(窗口可能越过上次位置)。
    """
    seen = load_seen_urls(vault_dir, state_dir)
    prior_seen = len(seen)
    run_date = datetime.now(CST).strftime("%Y-%m-%d")
    summary = {"feed_count": len(items), "ingested": 0, "market_intel": 0,
               "skipped_junk": 0, "duplicates": 0, "unprocessable": 0,
               "transient_fail": 0}
    entries = []
    for item in items:
        if not item.id or len(item.id) != 22:
            summary["unprocessable"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "unprocessable", "reasons": ["bad_id"]})
            continue
        if item.url in seen:
            summary["duplicates"] += 1
            continue
        seen.add(item.url)
        cls = classify(item)
        if cls.disposition == Disposition.SKIP_JUNK:
            summary["skipped_junk"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "skip_junk", "reasons": cls.reasons})
            continue
        body, src = to_body(item, fetch_fallback=fetch_fallback)
        if src == "deleted":
            summary["unprocessable"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "unprocessable", "reasons": ["deleted"]})
            continue
        if src == "empty":
            # 瞬时抓取失败:不记台账(下轮可重试),仅计数
            summary["transient_fail"] += 1
            continue
        if cls.disposition == Disposition.MARKET_INTEL:
            stage_market_intel(item, body, state_dir, run_date, cls.reasons)
            summary["market_intel"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "market_intel", "reasons": cls.reasons})
            continue
        path = write_commentary(item, body, vault_dir)
        summary["ingested"] += 1
        entries.append({"id": item.id, "url": item.url, "disposition": "ingest",
                        "reasons": [], "file": path.name, "body_src": src})
    # 不漏 safeguard:有历史却与本轮零重叠 → 窗口可能已越过上次抓取位置(启发式)
    if prior_seen > 0 and summary["duplicates"] == 0 and summary["feed_count"] > 0:
        summary["coverage_warning"] = (
            "本轮与已见集合零重叠,feed 窗口可能已越过上次抓取位置;"
            "建议增大 feed limit 或提高跑批频率")
    record_dispositions(state_dir, entries)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="commentary RSS 入库")
    ap.add_argument("--feed-url", default=os.environ.get("WEWE_FEED_URL", ""))
    ap.add_argument("--auth-code", default=os.environ.get("WEWE_AUTH_CODE", ""))
    ap.add_argument("--vault-dir", default=os.environ.get("VAULT_DIR", ""))
    ap.add_argument("--state-dir", default=os.environ.get("STATE_DIR", "state"))
    ap.add_argument("--db-path", default=os.environ.get("WEWE_DB_PATH", ""))
    ap.add_argument("--alert-webhook", default=os.environ.get("ALERT_WEBHOOK_URL", ""))
    ap.add_argument("--check-token", action="store_true")
    ap.add_argument("--no-fallback", action="store_true",
                    help="不做正文兜底抓取(只用 feed 全文)")
    ap.add_argument("--feed-timeout", type=int,
                    default=int(os.environ.get("WEWE_FEED_TIMEOUT", "120")),
                    help="拉 feed 的超时秒数(fulltext 大 feed 需调大,默认 120)")
    ap.add_argument("--since", default=os.environ.get("WEWE_SINCE", ""),
                    help="日期下限 YYYY-MM-DD;date 早于此的 feed item 跳过")
    args = ap.parse_args()

    # 严格校验 --since 格式(防错误格式静默全丢)
    try:
        validate_since(args.since)
    except ValueError:
        ap.error(f"--since 格式须为 YYYY-MM-DD(收到: {args.since!r})")

    # token 健康检查。注意:token 失效时**不中止入库**——wewe-rss 仍能 serve 已存
    # 文章的 feed(token 只挡"发现新文章"),故照常消费并告警提醒补扫。
    st = check_token(Path(args.db_path)) if args.db_path else None
    if st is not None and not st.valid:
        msg = f"[commentary-ingest] wewe-rss token 失效:{st.detail}（账号 {st.account_name}）需重新扫码"
        if not alert(msg, args.alert_webhook):
            print(msg)
    if args.check_token:
        if st is None:
            ap.error("--check-token 需 --db-path")
        print(f"token valid={st.valid} detail={st.detail}")
        return 0 if st.valid else 1

    if not args.feed_url or not args.vault_dir:
        ap.error("缺 --feed-url / --vault-dir(或对应 env)")
    items = fetch_feed(args.feed_url, args.auth_code, timeout=args.feed_timeout)
    items = filter_since(items, args.since)
    summary = ingest_items(items, vault_dir=Path(args.vault_dir),
                           state_dir=Path(args.state_dir),
                           fetch_fallback=not args.no_fallback)
    if summary.get("coverage_warning"):
        cov = f"[commentary-ingest] 覆盖告警:{summary['coverage_warning']}"
        if not alert(cov, args.alert_webhook):
            print(cov)
    token_status = "unknown" if st is None else ("valid" if st.valid else "invalid")
    write_last_run(Path(args.state_dir), {**summary, "token_status": token_status})
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
