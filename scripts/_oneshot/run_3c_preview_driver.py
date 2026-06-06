#!/usr/bin/env python3
"""③-C Task10 全量 preview 驱动器(并发 judge · 断点续跑)。

为什么单独写 driver:run.py 的 run_preview 是串行、无续跑、judge 网络异常会崩整轮。
3075 候选串行 ~7h、中途一断全丢。这里:
  1. 候选生成 + 程序门 = 全局一次性(跨篇找关系,不能按 pid 分块),进程内完成(快)。
  2. judge 阶段 = ThreadPoolExecutor 并发 + 每条判完即写 judge_results.jsonl(按 candidate_id 续跑);
     单条网络失败 → 记 manual_review(judge_error),不崩整轮。
  3. partition + 写 4 个 JSONL + summary + HTML = 复用 run.py / program_gate / report。

只 preview:不写 vault、不写 raw、不 apply、不进 ④。

环境变量:OPENAI_BASE_URL / OPENAI_API_KEY(deepseek 端点),见 models.env。
用法(孤儿化跑):
  set -a; . ~/.config/policy-pipeline/models.env; set +a
  OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \\
  STATE=state/node3c/sem_preview_20260606 JUDGE_MODEL=$DEEPSEEK_MODEL CONC=10 \\
  nohup caffeinate -i python3 -m scripts._oneshot.run_3c_preview_driver >"$STATE.log" 2>&1 & disown
"""
from __future__ import annotations
import json, os, threading, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.analysis_semantic_relations.loaders import load_policy_views, load_hpr_basis_pairs
from scripts.analysis_semantic_relations.candidates import generate_candidates
from scripts.analysis_semantic_relations.judge import judge_candidate
from scripts.analysis_semantic_relations import program_gate
from scripts.analysis_semantic_relations.report import render_preview_html
from scripts.common.llm import OpenAICompatClient

VAULT = os.environ.get("VAULT", str(Path.home() / "Documents" / "Zayn Main" / "政策分析"))
STATE = Path(os.environ.get("STATE", "state/node3c/sem_preview"))
HPR = os.environ.get(
    "HPR", "state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL") or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
CONC = int(os.environ.get("CONC", "10"))

_lock = threading.Lock()


def _read_done(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["candidate_id"]] = r
    return out


def _write_jsonl(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatClient(model=JUDGE_MODEL, log_path=str(STATE / "judge_calls.jsonl"))

    print(f"[3c] 载入 views + basis…", flush=True)
    views = load_policy_views(vault=VAULT)
    basis = load_hpr_basis_pairs(HPR)
    candidates = [c.to_row() for c in generate_candidates(views, basis)]
    valid = [c for c in candidates if not program_gate.check_candidate_row(c)]
    gate_fail = len(candidates) - len(valid)
    print(f"[3c] 候选 {len(candidates)} · 程序门通过 {len(valid)} · gate_failed {gate_fail}", flush=True)

    results_path = STATE / "judge_results.jsonl"
    done = _read_done(results_path)
    todo = [c for c in valid if c["candidate_id"] not in done]
    print(f"[3c] 已判 {len(done)} · 待判 {len(todo)} · 并发 {CONC} · judge={JUDGE_MODEL}", flush=True)

    def _judge(c):
        try:
            v = judge_candidate(client, c)
            return c["candidate_id"], v.decision, v.confidence, v.reason, v.model
        except Exception as e:  # 单条持续失败 → 记 manual_review,不崩整轮
            return c["candidate_id"], "manual_review", 0.0, f"judge_error: {type(e).__name__}", JUDGE_MODEL

    n_done = len(done)
    if todo:
        rf = results_path.open("a", encoding="utf-8")
        try:
            with ThreadPoolExecutor(max_workers=CONC) as ex:
                futs = {ex.submit(_judge, c): c for c in todo}
                for fut in as_completed(futs):
                    cid, decision, conf, reason, model = fut.result()
                    rec = {"candidate_id": cid, "decision": decision,
                           "confidence": conf, "reason": reason, "model": model}
                    with _lock:
                        rf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        rf.flush()
                        done[cid] = rec
                        n_done += 1
                        if n_done % 100 == 0:
                            print(f"[3c] judged {n_done}/{len(valid)}", flush=True)
        finally:
            rf.close()
    print(f"[3c] judge 完成 · 共 {len(done)} 结果", flush=True)

    # 回填判定到候选行 + partition
    judgments = {}
    for c in valid:
        r = done.get(c["candidate_id"])
        if r:
            judgments[c["candidate_id"]] = r["decision"]
            c["confidence"] = r["confidence"]
            c["judge_reason"] = r["reason"]
            c["model"] = r["model"]
    accepted, manual = program_gate.partition_by_decision(valid, judgments)

    summary = {
        "candidate_count": len(candidates),
        "gate_failed": gate_fail,
        "judged": len(done),
        "accepted_count": len(accepted),
        "manual_count": len(manual),
        "accepted_by_relation": dict(Counter(c["rel"] for c in accepted)),
        "manual_by_relation": dict(Counter(c["rel"] for c in manual)),
        "decision_dist": dict(Counter(r["decision"] for r in done.values())),
        "model": JUDGE_MODEL,
        "recommendation": "preview_only_no_apply",
        "notes": ["no_vault_write", "no_raw_write", "no_apply",
                  "manual_review_not_in_accepted", "old_relations_not_used_as_accepted",
                  "judge=cycle1_locked_conservative_aligns"],
    }
    _write_jsonl(STATE / "semantic_relation_candidates.jsonl", candidates)
    _write_jsonl(STATE / "accepted_semantic_relations.jsonl", accepted)
    _write_jsonl(STATE / "manual_review_queue.jsonl", manual)
    (STATE / "semantic_relation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = render_preview_html(summary, accepted, manual, STATE / "reports" / "semantic_relation_preview.html")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"[3c] report: {report}", flush=True)
    print("[3c] ALL DONE", flush=True)


if __name__ == "__main__":
    main()
