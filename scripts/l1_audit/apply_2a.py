"""Phase-2 apply 2a 编排:确定性 dedup(运行时重算) + 读 decisions(archive / market_intel)
→ 调 apply 原语移文件。market_intel 只登记不动。manifest/log 落 pipeline state/。
只动 0_raw,不碰派生层(③整体重建)。所有移动可逆(checkpoint tag + git 历史)。"""
from __future__ import annotations
import json
import argparse
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.l1_audit.dedup_group import group_duplicates
from scripts.l1_audit.apply import archive_policy, move_duplicate


def run_2a(policies_dir: str, archive_dir: str, duplicates_dir: str,
           manifest_path: str, log_path: str, decisions: dict, date: str) -> dict:
    log: list[dict] = []

    # 1) dedup —— 确定性,运行时重算(不信任何过期清单)
    for f in group_duplicates(load_policies(policies_dir)):
        keep = f.detail["keep"]
        for dup in f.detail["dups"]:
            dst = move_duplicate(policies_dir, dup, keep, duplicates_dir, date)
            log.append({"action": "dedup_move", "pid": dup, "keep": keep, "dst": dst, "at": date})

    # 2) archive 真噪声
    reasons = decisions.get("archive_reasons", {})
    for pid in decisions.get("archive", []):
        dst = archive_policy(policies_dir, pid, archive_dir)
        log.append({"action": "archive", "pid": pid, "dst": dst, "reason": reasons.get(pid, ""), "at": date})

    # 3) market_intel —— 不移不改,只写 manifest
    manifest = []
    for item in decisions.get("market_intel", []):
        manifest.append({
            "pid": item["pid"], "title": item.get("title", ""),
            "class": "market_intel", "kept_in": "0_raw/policies",
            "classified_by": "claude_agent_news_review_2026-05-31",
            "note": "第三源推后 BACKLOG B1",
        })

    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        for m in manifest:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    with open(log_path, "w", encoding="utf-8") as fh:
        for entry in log:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "dedup_moved": sum(1 for e in log if e["action"] == "dedup_move"),
        "archived": sum(1 for e in log if e["action"] == "archive"),
        "market_intel": len(manifest),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="vault 根(含 0_raw/)")
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--out-dir", default="state/source_ready")
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    vault = Path(args.vault)
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    summary = run_2a(
        policies_dir=str(vault / "0_raw" / "policies"),
        archive_dir=str(vault / "0_raw" / "_archive" / "policies" / f"source_audit_{args.date}"),
        duplicates_dir=str(vault / "0_raw" / "_duplicates"),
        manifest_path=str(Path(args.out_dir) / "market_intel_manifest.jsonl"),
        log_path=str(Path(args.out_dir) / "apply_log.jsonl"),
        decisions=decisions, date=args.date,
    )
    print(f"[apply 2a] {summary}")


if __name__ == "__main__":
    main()
