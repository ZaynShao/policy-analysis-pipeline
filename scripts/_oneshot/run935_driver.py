#!/usr/bin/env python3
"""②-B 全量 935 dry-run 驱动器(分块·可断点续跑)。

为什么分块:run_2b 的 plan() 是全量顺序循环、无断点续跑,935 篇约 6h,
中途任何中断都会从头重来。这里把 935 拆成若干 chunk,每块独立 subprocess、
各写自己的 state 子目录、完成打 _DONE 标记;重跑时已 _DONE 的块直接跳过。
全部完成后把各块的 drafts/queue 合并到 merged/,供 apply-accepted 离线消费。

这是编排器,不改 pipeline 核心逻辑(gen/judge/gate 仍走 run_2b)。
模型与端点经环境变量传入(GEN_MODEL/JUDGE_MODEL + ANTHROPIC_*/OPENAI_*)。
"""
import json, os, subprocess, sys, time
from pathlib import Path
from scripts.l1_audit.corpus import load_policies

VAULT = os.environ.get("VAULT", str(Path.home() / "Documents" / "Zayn Main" / "政策分析"))
STATE_ROOT = os.environ.get("STATE_ROOT", "state/node2b/run935")
CHUNK = int(os.environ.get("CHUNK", "100"))
GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic")
JUDGE_PROVIDER = os.environ.get("JUDGE_PROVIDER", "openai")
GEN_MODEL = os.environ["GEN_MODEL"]
JUDGE_MODEL = os.environ["JUDGE_MODEL"]


def _launch(i, ch):
    cdir = Path(STATE_ROOT) / f"chunk_{i:02d}"
    cdir.mkdir(parents=True, exist_ok=True)
    pf = cdir / "pids.json"
    pf.write_text(json.dumps(ch, ensure_ascii=False), encoding="utf-8")
    log = open(cdir / "run.log", "w", encoding="utf-8")
    p = subprocess.Popen([
        sys.executable, "-m", "scripts.l2_themescore.run_2b", "dry-run",
        "--vault", VAULT, "--state", str(cdir), "--pid-file", str(pf),
        "--gen-provider", GEN_PROVIDER, "--gen-model", GEN_MODEL,
        "--judge-provider", JUDGE_PROVIDER, "--judge-model", JUDGE_MODEL,
    ], stdout=log, stderr=subprocess.STDOUT)
    return p, cdir, log


def run_chunks():
    conc = int(os.environ.get("CONC", "8"))
    pids = [r.pid for r in load_policies(f"{VAULT}/0_raw/policies")]
    chunks = [pids[i:i + CHUNK] for i in range(0, len(pids), CHUNK)]
    todo = [(i, ch) for i, ch in enumerate(chunks)
            if not (Path(STATE_ROOT) / f"chunk_{i:02d}" / "_DONE").exists()]
    print(f"[driver] {len(pids)} pids → {len(chunks)} chunks of ≤{CHUNK}; "
          f"{len(todo)} todo; conc={conc}; gen={GEN_MODEL} judge={JUDGE_MODEL}", flush=True)
    running = {}  # popen -> (i, cdir, log)
    idx, failed = 0, []
    while idx < len(todo) or running:
        while len(running) < conc and idx < len(todo):
            i, ch = todo[idx]; idx += 1
            p, cdir, log = _launch(i, ch)
            running[p] = (i, cdir, log)
            print(f"[driver] launch chunk {i:02d} ({len(ch)} pids) · running={len(running)}", flush=True)
        time.sleep(5)
        for p in list(running):
            if p.poll() is None:
                continue
            i, cdir, log = running.pop(p); log.close()
            if p.returncode == 0:
                (cdir / "_DONE").write_text("ok", encoding="utf-8")
                print(f"[driver] chunk {i:02d} DONE · {len(running)} still running · {len(todo)-idx} queued", flush=True)
            else:
                failed.append(i)
                print(f"[driver] chunk {i:02d} FAILED rc={p.returncode} (rerun resumes it)", flush=True)
    if failed:
        print(f"[driver] FAILED chunks: {sorted(failed)} — rerun driver to resume", flush=True)
        sys.exit(2)
    return chunks


def merge():
    merged = Path(STATE_ROOT) / "merged"
    (merged / "proposed_changes").mkdir(parents=True, exist_ok=True)
    (merged / "review_queue").mkdir(parents=True, exist_ok=True)
    df = merged / "proposed_changes" / "drafts_full.jsonl"
    ds = merged / "proposed_changes" / "drafts.jsonl"
    q = merged / "review_queue" / "queue.jsonl"
    n_df = n_q = 0
    with df.open("w", encoding="utf-8") as fdf, ds.open("w", encoding="utf-8") as fds, q.open("w", encoding="utf-8") as fq:
        for cdir in sorted((Path(STATE_ROOT)).glob("chunk_*")):
            for line in (cdir / "proposed_changes" / "drafts_full.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    fdf.write(line + "\n"); n_df += 1
            sp = cdir / "proposed_changes" / "drafts.jsonl"
            if sp.exists():
                for line in sp.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        fds.write(line + "\n")
            qp = cdir / "review_queue" / "queue.jsonl"
            if qp.exists():
                for line in qp.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        fq.write(line + "\n"); n_q += 1
    print(f"[driver] merged → accepted(drafts) {n_df} · 入队 {n_q} · at {merged}", flush=True)
    summary = {"accepted": n_df, "queued": n_q, "gen_model": GEN_MODEL, "judge_model": JUDGE_MODEL}
    (merged / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_chunks()
    merge()
    print("[driver] ALL DONE", flush=True)
