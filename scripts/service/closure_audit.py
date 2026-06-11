"""S2 闭环日巡检。host python 只读:检查产线活性、vault 纯净并按需 notify。"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from scripts.service import notify


STATE_THRESHOLDS_HOURS = [
    ("commentary_ingest/last_run.json", 26),
    ("relations_increment/hpr", 26),
    ("derived_signals/nightly", 26),
    ("signal_context/nightly", 26),
    ("analysis_layer/nightly", 26),
    ("last_sync_run.json", 26),
]

PRODUCT_PATH_PREFIXES = (
    "0_raw/",
    "1_extracted/",
    "_meta/business_view/",
)
VPS_AUTHOR = "policy-pipeline-vps"


def _git(vault: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=vault,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


def check_state_activity(state_dir: Path, *, now: float | None = None) -> list[str]:
    state_dir = Path(state_dir)
    now = time.time() if now is None else now
    violations = []

    for rel, threshold_hours in STATE_THRESHOLDS_HOURS:
        path = state_dir / rel
        if not path.exists():
            violations.append(f"state {rel} 缺失")
            continue
        age_hours = (now - path.stat().st_mtime) / 3600
        if age_hours > threshold_hours:
            violations.append(
                f"state {rel} 超龄 {age_hours:.1f}h > {threshold_hours}h"
            )

    sync_path = state_dir / "last_sync_run.json"
    if sync_path.exists():
        try:
            data = json.loads(sync_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        errors = data.get("errors")
        if errors:
            violations.append(f"last_sync_run.json errors 非空: {len(errors)}")

    return violations


def _changed_paths(vault: Path, commit: str) -> list[str]:
    out = _git(
        vault,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        commit,
    )
    return [line for line in out.splitlines() if line]


def check_vault_git(vault: Path) -> list[str]:
    vault = Path(vault)
    violations = []

    status = _git(vault, "status", "--porcelain")
    if status:
        violations.append("vault 工作树不干净")

    head = _git(vault, "rev-parse", "HEAD")
    origin_main = _git(vault, "rev-parse", "origin/main")
    if head != origin_main:
        violations.append(f"vault HEAD != origin/main: {head[:12]} != {origin_main[:12]}")

    log = _git(vault, "log", "-n", "20", "--format=%H%x00%an")
    for line in log.splitlines():
        if not line:
            continue
        commit, author = line.split("\x00", 1)
        product_paths = [
            path
            for path in _changed_paths(vault, commit)
            if path.startswith(PRODUCT_PATH_PREFIXES)
        ]
        if product_paths and author != VPS_AUTHOR:
            violations.append(
                f"产物路径非 VPS 作者: {commit[:12]} {author} {product_paths[0]}"
            )

    return violations


def run_audit(vault: Path, state_dir: Path) -> tuple[list[str], dict[str, int]]:
    state_violations = check_state_activity(state_dir)
    vault_violations = check_vault_git(vault)
    product_commits = 0
    for line in _git(Path(vault), "log", "-n", "20", "--format=%H").splitlines():
        if any(
            path.startswith(PRODUCT_PATH_PREFIXES)
            for path in _changed_paths(Path(vault), line)
        ):
            product_commits += 1
    checked = {
        "state_paths": len(STATE_THRESHOLDS_HOURS),
        "vault_product_commits": product_commits,
    }
    return state_violations + vault_violations, checked


def _format_alert(violations: list[str]) -> str:
    lines = "\n".join(f"- {item}" for item in violations)
    return f"[S2] 闭环巡检异常 {len(violations)} 项:\n{lines}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    violations, checked = run_audit(Path(args.vault), Path(args.state_dir))
    if violations:
        msg = _format_alert(violations)
        if args.dry_run:
            print(msg)
        else:
            notify.send_text(msg)
        return 1

    print(json.dumps({"ok": True, "checked": checked}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
