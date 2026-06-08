"""从 L1 真实残留生成 fixture 池行,供 B14 闭环建/验/演示。

**这不是正式 backfill**(正式 backfill 是 L1 的 IN 活,见 plan 协调依赖)。
只读 L1 残留(ferr.txt 等),用纯构造函数生成池行,经 review_pool.append 写到独立
fixture 池(默认 state/l1_review/pool.fixture.jsonl),不污染真 pool。

构造函数(纯,可测);main(--emit) 读真文件。
"""
import argparse
from pathlib import Path

# L1 残留来源(l1-repair worktree)。可用 --source 覆盖。
DEFAULT_QUAR = Path(
    "/Users/shaoziyuan/dev/政策分析-pipeline-l1-repair/state/T1_incremental/quar")


def fetch_fail_row(channel: str, domain: str, url: str, reason: str) -> dict:
    """一条抓取失败 URL → fetch_fail 池行。"""
    return {"kind": "fetch_fail", "ref": url,
            "reason": reason, "suggested_action": "retry",
            "confidence": None, "evidence": f"{channel} {domain}"[:80],
            "channel": channel, "run_label": "seed_fixture"}


def checkpoint_row(domain: str, city: str, list_url: str) -> dict:
    """一个待核验候选渠道 → checkpoint 池行。"""
    return {"kind": "checkpoint", "ref": domain,
            "reason": "discovery_candidate_unverified", "suggested_action": "promote",
            "confidence": None, "evidence": f"{city} {list_url}"[:80],
            "channel": city, "run_label": "seed_fixture"}


def parse_ferr_filename(name: str):
    """'{channel}__{type}__{domain}__ferr.txt' → (channel, domain)。"""
    stem = name[:-len("__ferr.txt")] if name.endswith("__ferr.txt") else name
    parts = stem.split("__")
    channel = parts[0]
    domain = parts[2] if len(parts) >= 3 else (parts[-1] if parts else "")
    return channel, domain


def iter_fetch_fail_rows(quar_dir: Path):
    """遍历 quar/*ferr.txt,每行失败 URL → 一条 fetch_fail 行。"""
    for ferr in sorted(quar_dir.glob("*__ferr.txt")):
        channel, domain = parse_ferr_filename(ferr.name)
        for line in ferr.read_text(encoding="utf-8").splitlines():
            url = line.strip()
            if url:
                yield fetch_fail_row(channel, domain, url, reason="fetch_failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_QUAR,
                    help="L1 quar 目录(含 *__ferr.txt)")
    ap.add_argument("--emit", type=Path,
                    default=Path("state/l1_review/pool.fixture.jsonl"),
                    help="fixture 池输出路径")
    args = ap.parse_args()

    from scripts.l1_collect.review_pool import append
    n = 0
    for row in iter_fetch_fail_rows(args.source):
        if append(row, pool_path=args.emit):
            n += 1
    print(f"seeded {n} fetch_fail rows → {args.emit}")


if __name__ == "__main__":
    main()
