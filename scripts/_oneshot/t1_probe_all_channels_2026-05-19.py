"""对 channel_catalog 中所有 status=候选 的渠道跑 connectivity_probe。

并发 16 workers,timeout 短一些(政府网正常应快响应);失败的 fall back 到
http://(政府网很多不强制 https)再试一次。
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import (
    Channel, ChannelStatus, load_catalog, save_catalog,
)
from scripts.l1_collect.connectivity_probe import probe_url

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
PROBE_LOG = ROOT / "state" / "T1_channels" / "channel_probe_log.jsonl"

MAX_WORKERS = 16
SLEEP_BETWEEN = 0.05


def _try_url(url: str):
    res = probe_url(url)
    return res


def probe_one(ch: Channel) -> tuple[Channel, dict]:
    # 先 https,失败 fall back http
    https_url = ch.list_url or f"https://{ch.root_domain}/"
    res = _try_url(https_url)
    used_url = https_url
    if res.verdict == "http_error":
        http_url = https_url.replace("https://", "http://", 1)
        res2 = _try_url(http_url)
        if res2.verdict != "http_error":
            res = res2
            used_url = http_url
    log = {
        "timestamp": res.probed_at, "city": ch.city, "channel_type": ch.channel_type,
        "root_domain": ch.root_domain, "url": used_url, "http_status": res.http_status,
        "page_has_list_pattern": res.page_has_list_pattern, "verdict": res.verdict,
        "error": res.error, "source": ch.source,
    }
    ch.last_probed_at = res.probed_at
    ch.probe_result = res.verdict
    if res.verdict == "ok":
        ch.status = ChannelStatus.验证
        if used_url != ch.list_url:
            ch.list_url = used_url  # 记下成功的 URL(可能从 https 降到 http)
    return ch, log


def main() -> None:
    catalog = load_catalog(CATALOG)
    pending = [c for c in catalog if c.status == ChannelStatus.候选]
    print(f"probing {len(pending)} channels with {MAX_WORKERS} workers")
    t0 = time.time()
    with open(PROBE_LOG, "a", encoding="utf-8") as logf:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(probe_one, c): c for c in pending}
            done = 0
            for fut in as_completed(futures):
                ch, log = fut.result()
                logf.write(json.dumps(log, ensure_ascii=False) + "\n")
                logf.flush()
                done += 1
                if done % 50 == 0:
                    elapsed = time.time() - t0
                    print(f"  {done}/{len(pending)} done ({elapsed:.0f}s elapsed)")
                time.sleep(SLEEP_BETWEEN)
    save_catalog(catalog, CATALOG)
    n_ok = sum(1 for c in catalog if c.status == ChannelStatus.验证)
    elapsed = time.time() - t0
    print(f"done in {elapsed:.0f}s: {n_ok}/{len(catalog)} channels verified")


if __name__ == "__main__":
    main()
