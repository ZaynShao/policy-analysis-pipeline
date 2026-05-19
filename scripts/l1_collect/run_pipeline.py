"""T1 总入口:按 batch 跑 Step 2-5。

Usage:
  python3 -m scripts.l1_collect.run_pipeline --batch P0
  python3 -m scripts.l1_collect.run_pipeline --batch P0 --dry-run
  python3 -m scripts.l1_collect.run_pipeline --cities 杭州市,成都市
"""
from __future__ import annotations
import argparse
from pathlib import Path
import yaml

from .channel_catalog import load_catalog, ChannelStatus
from .step2_scan import scan_channel
from .step3_filter import filter_scan_rows
from .step4_fetch import fetch_candidates
from .step4_5_extract import extract_all
from .step5_ingest import ingest_extracted
from .dedup import DedupIndex

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
VAULT_POLICIES = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "0_raw" / "policies"


def _resolve_cities(args) -> list:
    if args.cities:
        return [c.strip() for c in args.cities.split(",")]
    pri = STATE / "T1_channels" / "city_priority.yaml"
    p = yaml.safe_load(pri.read_text(encoding="utf-8"))
    return [x["city"] for x in p["batches"][args.batch]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", choices=["P0", "P1", "P2"], default="P0")
    ap.add_argument("--cities", help="逗号分隔城市名,覆盖 --batch")
    ap.add_argument("--dry-run", action="store_true",
                    help="只跑 Step 2-3,不抓不入库")
    args = ap.parse_args()

    cities = _resolve_cities(args)
    label = args.cities or args.batch
    print(f"[run_pipeline] batch={args.batch} cities={len(cities)} dry_run={args.dry_run}")

    catalog = load_catalog(STATE / "T1_channels" / "channel_catalog.yaml")
    channels = [c for c in catalog if c.city in cities and c.status == ChannelStatus.验证]
    print(f"[run_pipeline] verified channels matched: {len(channels)}")
    if not channels:
        print("[run_pipeline] no verified channels for this batch, abort")
        return

    # Step 2
    scan_dir = STATE / "T1_scan_raw"
    scan_dir.mkdir(exist_ok=True)
    total_scan = 0
    for ch in channels:
        n = scan_channel(ch, scan_dir)
        print(f"  [Step2] {ch.city:10s} {ch.channel_type:6s} {ch.root_domain:30s} -> {n} rows")
        total_scan += n
    print(f"[Step 2] total scanned: {total_scan}")

    # Step 3
    cand_dir = STATE / "T1_candidate"
    quar_dir = STATE / "T1_quarantine"
    cand_dir.mkdir(exist_ok=True); quar_dir.mkdir(exist_ok=True)
    print("[Step 3] building dedup index from vault...")
    dedup_idx = DedupIndex.from_vault_policies(VAULT_POLICIES)
    print(f"[Step 3] dedup index: {len(dedup_idx.url_hashes)} URLs / "
          f"{len(dedup_idx.offnum_hashes)} offnums / {len(dedup_idx.title_hashes)} titles")
    # merge 所有 scan 输出到一个临时文件
    merged = scan_dir / f"_merged_{label}.jsonl"
    with open(merged, "w", encoding="utf-8") as out:
        for f in scan_dir.glob("*.jsonl"):
            if f.name.startswith("_"):
                continue
            content = f.read_text(encoding="utf-8")
            out.write(content)
            if content and not content.endswith("\n"):
                out.write("\n")
    cand_file = cand_dir / f"{label}.jsonl"
    quar_file = quar_dir / f"{label}__step3.jsonl"
    kept, drop = filter_scan_rows(merged, cand_file, quar_file, dedup_idx)
    print(f"[Step 3] kept {kept}, dropped {drop} (quarantine: {quar_file.name})")

    if args.dry_run:
        print("[dry-run] stop after Step 3")
        return

    # Step 4
    fetch_dir = STATE / "T1_fetched"
    err_log = fetch_dir / f"{label}__fetch_errors.txt"
    fetch_dir.mkdir(exist_ok=True)
    ok, err = fetch_candidates(cand_file, fetch_dir, err_log)
    print(f"[Step 4] fetched ok={ok} err={err}")

    # Step 4.5
    extract_dir = STATE / "T1_extracted"
    quar_45 = quar_dir / f"{label}__step45.jsonl"
    extract_dir.mkdir(exist_ok=True)
    ext_ok, ext_quar = extract_all(fetch_dir, extract_dir, quar_45)
    print(f"[Step 4.5] extracted={ext_ok} quarantined={ext_quar}")

    # Step 5
    ingest_log_dir = STATE / "T1_ingest_log"
    ingest_log_dir.mkdir(exist_ok=True)
    ingest_log = ingest_log_dir / f"{label}.jsonl"
    ing_ok, ing_fail = ingest_extracted(extract_dir, ingest_log)
    print(f"[Step 5] ingested={ing_ok} failed={ing_fail}")
    print(f"[run_pipeline] DONE batch={label}")


if __name__ == "__main__":
    main()
