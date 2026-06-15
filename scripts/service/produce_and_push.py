"""生产后 git 收尾:add(白名单)→ commit → pull --rebase → push。

所有生产 cron 共用。exit:0=成功/无变更;4=白名单外改动(告警不提交);
5=push 失败(本地 commit 保留,下轮 cron 重试;期间 sync_tick 守卫会 abort 不 reset)。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.service.notify import send_text as notify_send


def _git(args: list, cwd) -> str:
    res = subprocess.run(["git", *args], cwd=str(cwd), check=True,
                         capture_output=True, text=True)
    return res.stdout.strip()


def classify_changes(porcelain: str, whitelist: list) -> tuple:
    """git status --porcelain -z 输出 → (白名单内路径, 白名单外路径)。
    -z:NUL 分隔、文件名原样不转义(内嵌换行/制表符等控制字符不会拆条目或被转义,
    否则 git add 拿到转义名找不到真文件会退 128 崩管线);R/C 条目后随一个 NUL 终止的原路径字段。"""
    to_add, violations = [], []
    records = porcelain.split("\0")
    i = 0
    while i < len(records):
        rec = records[i]
        if not rec:
            i += 1
            continue
        status, path = rec[:2], rec[3:]        # "XY " 前缀:2 状态位 + 空格
        if "R" in status or "C" in status:     # rename/copy:原路径在随后一条,跳过,只按新路径分类
            i += 1
        (to_add if any(path.startswith(w) for w in whitelist) else violations).append(path)
        i += 1
    return to_add, violations


def run(vault_dir, whitelist: list, message: str) -> int:
    vault_dir = Path(vault_dir)
    porcelain = subprocess.run(
        ["git", "-c", "core.quotepath=false", "status", "--porcelain", "-u", "-z"],
        cwd=str(vault_dir), check=True, capture_output=True, text=True).stdout
    to_add, violations = classify_changes(porcelain, whitelist)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if violations:
        msg = f"[produce_and_push] 白名单外改动,拒绝提交: {violations[:5]} (共{len(violations)})"
        print(f"[{ts}] {msg}", file=sys.stderr)
        notify_send(msg)
        return 4
    if not to_add:
        ahead = _git(["rev-list", "--count", "origin/main..HEAD"], vault_dir)
        if ahead != "0":
            try:
                _git(["pull", "--rebase", "origin", "main"], vault_dir)
                _git(["push", "origin", "main"], vault_dir)
            except subprocess.CalledProcessError as e:
                subprocess.run(["git", "rebase", "--abort"], cwd=str(vault_dir),
                               capture_output=True)
                msg = f"[produce_and_push] 滞留 commit 重推失败: {e.stderr[:200] if e.stderr else e}"
                print(f"[{ts}] {msg}", file=sys.stderr)
                notify_send(msg)
                return 5
            print(f"[{ts}] pushed stranded commits ({ahead})")
            return 0
        print(f"[{ts}] no change, skip")
        return 0
    _git(["add", "--", *to_add], vault_dir)
    _git(["commit", "-m", message], vault_dir)
    try:
        _git(["pull", "--rebase", "origin", "main"], vault_dir)
        _git(["push", "origin", "main"], vault_dir)
    except subprocess.CalledProcessError as e:
        subprocess.run(["git", "rebase", "--abort"], cwd=str(vault_dir),
                       capture_output=True)
        msg = f"[produce_and_push] push 失败(本地 commit 保留待重试): {e.stderr[:200] if e.stderr else e}"
        print(f"[{ts}] {msg}", file=sys.stderr)
        notify_send(msg)
        return 5
    print(f"[{ts}] pushed {len(to_add)} paths: {message}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-dir", required=True)
    ap.add_argument("--whitelist", required=True, help="逗号分隔路径前缀")
    ap.add_argument("--message", required=True)
    args = ap.parse_args(argv)
    return run(args.vault_dir, [w for w in args.whitelist.split(",") if w], args.message)


if __name__ == "__main__":
    raise SystemExit(main())
