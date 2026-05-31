"""2b 批次 dump(只读):取 id_issuer-flagged 列表,按 pid 排序,切第 N 批,
落 {pid,id_short,title,official_number,issuer,issuer_canonical,date,url,body_head}
供 agent(当 LLM)逐条读 → 判 class + 解析真 issuer/region。零变更。"""
from __future__ import annotations
import json
import argparse
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.l1_audit.id_issuer_check import check_corpus, parse_issuer_short


def dump_batch(policies_dir: str, out_dir: str, batch: int, size: int,
               body_chars: int = 1800) -> dict:
    recs = load_policies(policies_dir)
    by_pid = {r.pid: r for r in recs}
    flagged = sorted(check_corpus(recs), key=lambda f: f.pid)
    pids = [f.pid for f in flagged]
    start, end = (batch - 1) * size, batch * size
    chunk = pids[start:end]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"batch_{batch}_input.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for pid in chunk:
            r = by_pid[pid]
            fh.write(json.dumps({
                "pid": pid,
                "id_short": parse_issuer_short(pid),
                "title": r.title,
                "official_number": r.official_number,
                "issuer": r.issuer,
                "issuer_canonical": r.issuer_canonical,
                "date": r.date,
                "url": r.url,
                "body_head": (r.body_head or "")[:body_chars],
            }, ensure_ascii=False) + "\n")
    return {"total_flagged": len(pids), "batch": batch, "size": len(chunk),
            "range": [start, min(end, len(pids))], "out": str(out)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--out-dir", default="state/source_ready/go_sc_review")
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--size", type=int, default=40)
    ap.add_argument("--body-chars", type=int, default=1800)
    args = ap.parse_args()
    res = dump_batch(str(Path(args.vault) / "0_raw" / "policies"),
                     args.out_dir, args.batch, args.size, args.body_chars)
    print(f"[dump 2b] {res}")


if __name__ == "__main__":
    main()
