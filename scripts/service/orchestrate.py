"""L2 编排器。队列取 pid → 归属增量 → [结晶/分析钩子] → 账本 → 排空后 sync。

stage runner 注入式，便于测试。真实 runner（subprocess 调 run_2b）由工厂构造。
分析(语义关系)是 pairwise 全量、③-C 未 apply（spec P3）→ Phase 1 默认 no-op 钩子，
不在此硬造增量-pairwise 机制。
"""
from __future__ import annotations
import subprocess
import tempfile
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from scripts.service.hash_ledger import (
    LedgerEntry, needs_rebuild, mark_done, save_ledger,
)
from scripts.service import l2_queue


@dataclass
class StageResult:
    pid: str
    ok: bool
    error: str | None = None


def process_pid(pid: str, raw_text: str, version: int,
                ledger: dict[str, LedgerEntry],
                run_attribution: Callable[[str], None],
                run_crystallize: Callable[[str], None] | None = None) -> StageResult:
    if not needs_rebuild(pid, raw_text, version, ledger):
        return StageResult(pid, True, "skipped")
    try:
        run_attribution(pid)
        if run_crystallize is not None:
            run_crystallize(pid)
    except Exception as e:
        return StageResult(pid, False, str(e))
    mark_done(ledger, pid, raw_text, version)
    return StageResult(pid, True, None)


def drain_queue(queue_path: Path, ledger: dict, ledger_path: Path,
                raw_text_for: Callable[[str], str], version: int,
                run_attribution: Callable[[str], None],
                run_sync: Callable[[], None],
                run_crystallize: Callable[[str], None] | None = None) -> list[StageResult]:
    results: list[StageResult] = []
    processed_any = False
    while True:
        item = l2_queue.next_item(queue_path)
        if item is None:
            break
        try:
            raw_text = raw_text_for(item.pid)
        except Exception as e:
            results.append(StageResult(item.pid, False, f"raw_missing: {e}"))
            l2_queue.mark_complete(queue_path, item.pid)
            processed_any = True
            continue
        res = process_pid(item.pid, raw_text, version, ledger,
                          run_attribution, run_crystallize)
        results.append(res)
        l2_queue.mark_complete(queue_path, item.pid)
        save_ledger(ledger_path, ledger)
        processed_any = True
    if processed_any:
        run_sync()
    return results


# ---- 真实 stage runner 工厂（生产用，单测不覆盖 subprocess 本体）----

def make_attribution_runner(vault: str, state: str, gen_model: str, judge_model: str,
                            gen_provider: str = "anthropic",
                            judge_provider: str = "openai") -> Callable[[str], None]:
    """逐篇调 run_2b apply --pid-file（run_2b 已支持 --pid-file 限定 pid）。"""
    def run(pid: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump([pid], f)
            pid_file = f.name
        cmd = [
            "python3", "-m", "scripts.l2_themescore.run_2b", "apply",
            "--vault", vault, "--state", state, "--pid-file", pid_file,
            "--gen-model", gen_model, "--gen-provider", gen_provider,
            "--judge-model", judge_model, "--judge-provider", judge_provider,
        ]
        subprocess.run(cmd, check=True)
    return run
