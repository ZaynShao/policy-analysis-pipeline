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
from .models import Disposition, FeedItem
from .token_health import alert, check_token
from .writer import stage_market_intel, write_commentary

CST = timezone(timedelta(hours=8))


def ingest_items(items: list, *, vault_dir: Path, state_dir: Path,
                 fetch_fallback: bool = True) -> dict:
    """对一批 FeedItem 执行 去重→过滤→正文→写入→记账,返回 summary。"""
    seen = load_seen_urls(vault_dir, state_dir)
    run_date = datetime.now(CST).strftime("%Y-%m-%d")
    summary = {"feed_count": len(items), "ingested": 0, "market_intel": 0,
               "skipped_junk": 0, "duplicates": 0, "unprocessable": 0}
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
        if src == "empty":
            summary["unprocessable"] += 1
            entries.append({"id": item.id, "url": item.url,
                            "disposition": "unprocessable", "reasons": ["no_body"]})
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
    args = ap.parse_args()

    # token 健康检查(--check-token 或每轮入库前都查一次)
    if args.db_path:
        st = check_token(Path(args.db_path))
        if not st.valid:
            msg = f"[commentary-ingest] wewe-rss token 失效:{st.detail}（账号 {st.account_name}）需重新扫码"
            if not alert(msg, args.alert_webhook):
                print(msg)
        if args.check_token:
            print(f"token valid={st.valid} detail={st.detail}")
            return 0 if st.valid else 1

    if not args.feed_url or not args.vault_dir:
        ap.error("缺 --feed-url / --vault-dir(或对应 env)")
    items = fetch_feed(args.feed_url, args.auth_code)
    summary = ingest_items(items, vault_dir=Path(args.vault_dir),
                           state_dir=Path(args.state_dir),
                           fetch_fallback=not args.no_fallback)
    token_status = "valid"
    if args.db_path:
        token_status = "valid" if check_token(Path(args.db_path)).valid else "invalid"
    write_last_run(Path(args.state_dir), {**summary, "token_status": token_status})
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
