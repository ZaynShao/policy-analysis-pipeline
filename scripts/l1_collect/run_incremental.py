"""L1增量采集入口。service线调用,无调度逻辑。append-only。
流程:取锁→Step2分层扫→Step3规则过滤→Step4抓→Step4.5抽→policy_gate门→Step5入库→释放锁。
"""
from __future__ import annotations
import argparse
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .channel_catalog import load_catalog, ChannelStatus
from .step2_scan import scan_channel
from .step3_filter import filter_scan_rows
from .step4_fetch import fetch_candidates
from .step4_5_extract import extract_all
from .step5_ingest import ingest_extracted
from .dedup import DedupIndex
from .policy_gate import gate_one
from .common_llm_client import make_judge_client
from . import review_pool

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
VAULT_POLICIES = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "0_raw" / "policies"
LEVEL_MAP = {"national": "国家", "province": "省", "city": "市"}


@dataclass
class IncrementalConfig:
    level: list = field(default_factory=lambda: ["national", "province", "city"])
    since: str = "2026-01-01"
    dry_run: bool = False
    state_dir: Path = STATE / "T1_incremental"
    vault_dir: Path = VAULT_POLICIES
    channel_types: list = field(default_factory=list)


@contextmanager
def _l1_lock():
    """复用 service 的 l1_status 锁(若在树上);不在 → no-op(边界:不重复造锁)。"""
    try:
        from scripts.service.l1_status import acquire  # type: ignore
    except Exception:
        acquire = None
    if acquire is None:
        yield
        return
    with acquire():
        yield


def _select_channels(channels, levels: list, channel_types=None):
    cn = {LEVEL_MAP.get(l, l) for l in levels}
    out = [c for c in channels if c.level in cn and c.status == ChannelStatus.验证]
    if channel_types:
        out = [c for c in out if any(ct in c.channel_type for ct in channel_types)]
    return out


def _gate_extracted_dir(ext_dir: Path, passed_dir: Path, comm_dir: Path,
                        quar_jsonl: Path, llm_fn, *,
                        pool_path: Path = review_pool.POOL,
                        review_dir: Path = STATE / "T1_incremental" / "review",
                        run_label: str = "") -> tuple:
    passed_dir.mkdir(parents=True, exist_ok=True)
    comm_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    n_pass = n_comm = n_rej = n_review = 0
    rejects: list = []
    for jf in sorted(ext_dir.glob("*.json")):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        gr = gate_one(ref=jf.stem, url=rec.get("url", ""), title=rec.get("title", ""),
                      body_head=(rec.get("body") or "")[:800], llm_fn=llm_fn)
        if gr.action == "pass":
            (passed_dir / jf.name).write_text(jf.read_text(encoding="utf-8"),
                                              encoding="utf-8")
            n_pass += 1
        elif gr.action == "commentary":
            (comm_dir / jf.name).write_text(jf.read_text(encoding="utf-8"),
                                            encoding="utf-8")
            n_comm += 1
        elif gr.action == "review_queue":
            (review_dir / jf.name).write_text(jf.read_text(encoding="utf-8"),
                                              encoding="utf-8")
            try:
                review_pool.append({
                    "kind": "gate", "ref": jf.stem, "reason": gr.evidence or "low_conf",
                    "suggested_action": "review", "confidence": gr.confidence,
                    "evidence": rec.get("title", "")[:60], "channel": run_label,
                    "run_label": run_label}, pool_path=pool_path)
            except Exception as e:
                print(f"  [pool-write 失败] gate/{jf.stem}: {str(e)[:80]}")
            n_review += 1
        else:
            rejects.append({"file": jf.name, "url": rec.get("url", ""),
                            "title": rec.get("title", ""), **gr.to_dict()})
            n_rej += 1
    if rejects:
        quar_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(quar_jsonl, "a", encoding="utf-8") as f:
            for r in rejects:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n_pass, n_comm, n_rej, n_review


def _ingest_commentary(comm_ext_dir: Path, staging_dir: Path) -> int:
    """commentary extracted → ingest 成 staging raw(out_dir=staging)→ route_files 转 commentaries/。"""
    from scripts._oneshot.route_interpretations import route_files, build_title_index
    staging_dir.mkdir(parents=True, exist_ok=True)
    ingest_extracted(comm_ext_dir, staging_dir / "_ingest_log.jsonl", out_dir=staging_dir)
    paths = [p for p in staging_dir.glob("*.md")]
    if not paths:
        return 0
    idx = build_title_index(skip_paths=set())
    n = route_files(paths, index=idx, dry=False)
    (staging_dir / "_ingest_log.jsonl").unlink(missing_ok=True)
    return n


def _run_channel(ch, cfg: IncrementalConfig, dedup, llm_fn) -> dict:
    sd = cfg.state_dir
    for d in ["scan", "cand", "quar", "fetch", "ext", "passed", "comm_ext", "comm_stage", "ingest"]:
        (sd / d).mkdir(parents=True, exist_ok=True)
    label = f"{ch.city}__{ch.channel_type}__{ch.root_domain}"
    n_scan = scan_channel(ch, sd / "scan")
    if n_scan == 0:
        return {"channel": label, "scanned": 0, "ingested": 0}
    merged = sd / "scan" / f"_merged_{ch.root_domain}.jsonl"
    src = sd / "scan" / f"{label}.jsonl"
    merged.write_text(src.read_text(encoding="utf-8") if src.exists() else "",
                      encoding="utf-8")
    cand = sd / "cand" / f"{label}.jsonl"
    kept, _ = filter_scan_rows(merged, cand, sd / "quar" / f"{label}__s3.jsonl", dedup)
    if cfg.dry_run:
        return {"channel": label, "scanned": n_scan, "kept": kept, "ingested": 0}
    fetch_candidates(cand, sd / "fetch", sd / "quar" / f"{label}__ferr.txt")
    ferr = sd / "quar" / f"{label}__ferr.txt"
    if ferr.exists():
        for u in ferr.read_text(encoding="utf-8").split("\n"):
            if not u.strip():
                continue
            try:
                review_pool.append({
                    "kind": "fetch_fail", "ref": u.strip(),
                    "reason": "fetch_error_after_retry", "suggested_action": "retry",
                    "confidence": None, "evidence": "", "channel": label,
                    "run_label": label})
            except Exception as e:
                print(f"  [pool-write 失败] fetch_fail: {str(e)[:80]}")
    extract_all(sd / "fetch", sd / "ext", sd / "quar" / f"{label}__s45.jsonl")
    n_pass, n_comm, n_rej, n_review = _gate_extracted_dir(
        sd / "ext", sd / "passed", sd / "comm_ext",
        sd / "quar" / "gate_rejects.jsonl", llm_fn,
        review_dir=sd / "review", run_label=label)
    ing_ok, _ = ingest_extracted(sd / "passed", sd / "ingest" / f"{label}.jsonl")
    try:
        n_comm_ing = _ingest_commentary(sd / "comm_ext", sd / "comm_stage")
    except Exception as e:
        n_comm_ing = 0
        print(f"  [commentary-ingest 失败] {label[:40]}: {str(e)[:120]}")
    # 清空工作目录供下个渠道复用(避免跨渠道串;含 comm_stage 的 *.jsonl 暂存日志)
    for d in ["fetch", "ext", "passed", "comm_ext", "comm_stage"]:
        for pat in ("*.json", "*.md", "*.jsonl"):
            for f in (sd / d).glob(pat):
                f.unlink()
    return {"channel": label, "scanned": n_scan, "kept": kept,
            "gate_passed": n_pass, "gate_commentary": n_comm, "gate_rejected": n_rej,
            "gate_review": n_review,
            "ingested": ing_ok, "ingested_commentary": n_comm_ing}


def run_incremental(cfg: IncrementalConfig) -> dict:
    catalog = load_catalog(ROOT / "state/T1_channels/channel_catalog.yaml")
    channels = _select_channels(catalog, cfg.level, cfg.channel_types)
    print(f"[run_incremental] level={cfg.level} channels={len(channels)} dry={cfg.dry_run}")
    llm_fn = None if cfg.dry_run else make_judge_client()
    results = []
    with _l1_lock():
        dedup = DedupIndex.from_vault_policies(cfg.vault_dir)
        for ch in channels:
            r = _run_channel(ch, cfg, dedup, llm_fn)
            results.append(r)
            print(f"  {r['channel'][:48]:48s} scan={r['scanned']} ing={r.get('ingested',0)}")
    summary = {
        "channels_run": len(results),
        "total_scanned": sum(r["scanned"] for r in results),
        "total_ingested": sum(r.get("ingested", 0) for r in results),
        "total_commentary": sum(r.get("ingested_commentary", 0) for r in results),
        "total_gate_rejected": sum(r.get("gate_rejected", 0) for r in results),
        "total_gate_review": sum(r.get("gate_review", 0) for r in results),
        "dry_run": cfg.dry_run,
    }
    print(f"[run_incremental] DONE {summary}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="national,province,city")
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--channel-type", default="")
    a = ap.parse_args()
    run_incremental(IncrementalConfig(level=a.level.split(","), since=a.since,
                                      dry_run=a.dry_run,
                                      channel_types=[s for s in a.channel_type.split(",") if s]))


if __name__ == "__main__":
    main()
