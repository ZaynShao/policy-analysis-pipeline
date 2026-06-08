"""L2 worker CLI: drain queued policies through attribution and sync."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.l1_audit.corpus import load_policies
from scripts.service.hash_ledger import load_ledger
from scripts.service.orchestrate import (
    StageResult,
    drain_queue,
    make_attribution_runner,
)


def build_raw_text_for(vault):
    rec_by_pid = {r.pid: r for r in load_policies(f"{vault}/0_raw/policies")}

    def raw_text_for(pid):
        rec = rec_by_pid.get(pid)
        if rec is None:
            raise KeyError(f"pid 在 0_raw/policies 找不到原文: {pid}")
        return Path(rec.path).read_text(encoding="utf-8")

    return raw_text_for


def run(state_dir, version, raw_text_for, run_attribution, run_sync) -> list[StageResult]:
    state_dir = Path(state_dir)
    ledger_path = state_dir / "ledger.json"
    queue_path = state_dir / "l2_queue.jsonl"
    ledger = load_ledger(ledger_path)
    return drain_queue(queue_path, ledger, ledger_path, raw_text_for, version,
                       run_attribution, run_sync)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--pipeline-version", type=int, default=1)
    ap.add_argument("--gen-model")
    ap.add_argument("--gen-provider", default="anthropic")
    ap.add_argument("--judge-model")
    ap.add_argument("--judge-provider", default="openai")
    args = ap.parse_args(argv)

    raw_text_for = build_raw_text_for(args.vault)
    run_attribution = make_attribution_runner(
        args.vault,
        args.state_dir,
        args.gen_model,
        args.judge_model,
        args.gen_provider,
        args.judge_provider,
    )

    def run_sync():
        from scripts.sync import run_sync as sync_mod
        sync_mod.run(args.vault, args.state_dir, args.pipeline_version,
                     os.environ["DATABASE_URL"])

    results = run(args.state_dir, args.pipeline_version, raw_text_for, run_attribution, run_sync)
    summary = {
        "processed": len(results),
        "ok": sum(1 for r in results if r.ok),
        "failed": sum(1 for r in results if r.ok is False),
        "skipped": sum(1 for r in results if r.error == "skipped"),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
