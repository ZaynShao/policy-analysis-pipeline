"""Phase-2 apply 2b 编排:读 decisions 应用到 0_raw/policies。
顺序固定:dedup → archive → remint(就地) → market_intel(只登记) → commentary_defer(只 log)。
只动 0_raw,不碰派生层。所有移动可逆(checkpoint tag + git 历史)。manifest 幂等追加。"""
from __future__ import annotations
import json
import argparse
from pathlib import Path
from scripts.l1_audit.apply import archive_policy, move_duplicate, remint_id


def run_2b(policies_dir: str, archive_dir: str, duplicates_dir: str,
           manifest_path: str, log_path: str, decisions: dict) -> dict:
    date = decisions["date"]
    log: list[dict] = []

    # 1) dedup —— 按 decisions 显式清单
    for item in decisions.get("dedup", []):
        dst = move_duplicate(policies_dir, item["move"], item["keep"], duplicates_dir, date)
        log.append({"action": "dedup_move", "pid": item["move"],
                    "keep": item["keep"], "dst": dst, "at": date})

    # 2) archive 真噪声
    for item in decisions.get("archive", []):
        dst = archive_policy(policies_dir, item["pid"], archive_dir)
        log.append({"action": "archive", "pid": item["pid"], "dst": dst,
                    "reason": item.get("reason", ""), "at": date})

    # 3) remint —— 就地改 frontmatter,不移文件
    for item in decisions.get("remint", []):
        dst = remint_id(policies_dir, item["pid"], item["new_id"],
                        item["true_issuer"], item["true_region"],
                        fixed_at=date, date_fix=item.get("date_fix"))
        log.append({"action": "remint", "pid": item["pid"], "new_id": item["new_id"],
                    "dst": dst, "at": date})

    # 4) market_intel —— 不移不改,只幂等追加 manifest
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if Path(manifest_path).exists():
        for line in Path(manifest_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            existing.add(json.loads(line).get("pid"))
    appended = 0
    with open(manifest_path, "a", encoding="utf-8") as fh:
        for item in decisions.get("market_intel", []):
            pid = item["pid"]
            if pid in existing:
                log.append({"action": "market_intel", "pid": pid,
                            "manifest": "skip_existing", "at": date})
                continue
            fh.write(json.dumps({
                "pid": pid, "class": "market_intel", "kept_in": "0_raw/policies",
                "classified_by": "claude_agent_2b_2026-05-31",
                "note": "第三源推后 BACKLOG B1",
            }, ensure_ascii=False) + "\n")
            existing.add(pid)
            appended += 1
            log.append({"action": "market_intel", "pid": pid,
                        "manifest": "appended", "at": date})

    # 5) commentary_defer —— 不动文件,只 log
    for item in decisions.get("commentary_defer", []):
        log.append({"action": "commentary_defer", "pid": item["pid"],
                    "note": item.get("note", ""), "at": date})

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as fh:
        for entry in log:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "dedup_moved": sum(1 for e in log if e["action"] == "dedup_move"),
        "archived": sum(1 for e in log if e["action"] == "archive"),
        "reminted": sum(1 for e in log if e["action"] == "remint"),
        "market_intel": appended,
        "commentary_defer": sum(1 for e in log if e["action"] == "commentary_defer"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="vault 根(含 0_raw/)")
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--out-dir", default="state/source_ready")
    args = ap.parse_args()
    vault = Path(args.vault)
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    date = decisions["date"]
    summary = run_2b(
        policies_dir=str(vault / "0_raw" / "policies"),
        archive_dir=str(vault / "0_raw" / "_archive" / "policies" / f"source_audit_2b_{date}"),
        duplicates_dir=str(vault / "0_raw" / "_duplicates"),
        manifest_path=str(Path(args.out_dir) / "market_intel_manifest.jsonl"),
        log_path=str(Path(args.out_dir) / "apply_log_2b.jsonl"),
        decisions=decisions,
    )
    print(f"[apply 2b] {summary}")


if __name__ == "__main__":
    main()
