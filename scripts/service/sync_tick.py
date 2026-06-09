"""Stage 1 持续上云 tick(host 侧,cron 调度)。

git fetch vault → 远端 HEAD 变了才 reset 到最新 → docker compose run run_sync。
git/docker 经 subprocess;决策核(should_sync/build_run_sync_cmd)纯函数可测。
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def should_sync(local_sha: str, remote_sha: str) -> bool:
    """本地与远端 HEAD 都非空且不同 → 需同步。"""
    l, r = (local_sha or "").strip(), (remote_sha or "").strip()
    return bool(l) and bool(r) and l != r


def decide_sync_action(local_ahead: int, dirty: bool) -> str:
    """服务器有未推送的本地产物(领先提交)或工作树脏 → 中止报警,绝不 reset 删除;
    否则(纯消费者态)维持 reset --hard 的自清洁行为。"""
    if local_ahead > 0 or dirty:
        return "abort"
    return "reset"


def build_run_sync_cmd(*, compose_file: str, vault: str, state: str, version: int) -> list:
    """构造容器内跑 run_sync 的命令(便于测试/复用)。"""
    return [
        "docker", "compose", "-f", compose_file, "run", "--rm", "policy-pipeline",
        "python", "-m", "scripts.sync.run_sync",
        "--vault", vault, "--state-dir", state, "--pipeline-version", str(version),
    ]


def _git(args: list, cwd: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-dir", required=True)
    ap.add_argument("--pipeline-dir", required=True)
    ap.add_argument("--compose-file", required=True)
    ap.add_argument("--container-vault", default="/vault")
    ap.add_argument("--container-state", default="/state")
    ap.add_argument("--pipeline-version", type=int, default=1)
    ap.add_argument("--branch", default="main")
    args = ap.parse_args(argv)

    ts = datetime.now(CST).isoformat(timespec="seconds")
    try:
        _git(["fetch", "--depth=1", "origin", args.branch], args.vault_dir)
        local = _git(["rev-parse", "HEAD"], args.vault_dir)
        remote = _git(["rev-parse", f"origin/{args.branch}"], args.vault_dir)
    except subprocess.CalledProcessError as e:
        print(f"[{ts}] git error: {e.stderr or e}", file=sys.stderr)
        return 2

    if not should_sync(local, remote):
        print(f"[{ts}] no change (HEAD={local[:8]}), skip sync")
        return 0

    local_ahead = int(_git(["rev-list", "--count", f"origin/{args.branch}..HEAD"], args.vault_dir) or "0")
    dirty = bool(_git(["status", "--porcelain"], args.vault_dir))
    if decide_sync_action(local_ahead, dirty) == "abort":
        # 服务器有未推送本地产物:绝不 reset 删除。
        # TODO(S2): 接 Notification 告警通道;S1 阶段先 stderr + 非零退出码由 cron 日志捕获。
        print(f"[{ts}] sync_tick 中止:服务器 vault 有未推送本地改动"
              f"(领先 {local_ahead} 提交, dirty={dirty}),不执行 reset 以免误删",
              file=sys.stderr)
        return 3

    _git(["reset", "--hard", f"origin/{args.branch}"], args.vault_dir)
    print(f"[{ts}] vault {local[:8]} -> {remote[:8]}, running run_sync")
    cmd = build_run_sync_cmd(
        compose_file=args.compose_file,
        vault=args.container_vault, state=args.container_state,
        version=args.pipeline_version,
    )
    proc = subprocess.run(cmd, cwd=args.pipeline_dir)
    print(f"[{ts}] run_sync exit={proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
