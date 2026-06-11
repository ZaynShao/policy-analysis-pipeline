"""③ 关系族增量编排器。

只做增量编排与 relations apply:
- 新 pid 只和存量候选集合交叉判定,避免全量重判。
- ③-D 仍确定性全量重生 canonical/views。
- produce_and_push 不在本模块内,由 cron 下一段负责。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from scripts.analysis_high_precision_relations import run as hpr_run
from scripts.analysis_relation_views.run import run_preview as run_relation_views_preview
from scripts.analysis_semantic_relations import program_gate
from scripts.analysis_semantic_relations.candidates import generate_candidates
from scripts.analysis_semantic_relations.judge import judge_candidate
from scripts.analysis_semantic_relations.loaders import load_hpr_basis_pairs, load_policy_views
from scripts.service.notify import send_text

PID_LEDGER = "relations_pid_ledger.json"
SEM_ACCEPTED = "sem_accepted_cumulative.jsonl"
JUDGED_LEDGER = "relations_judged_ledger.jsonl"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def select_new_pids(tracked_pids: list[str], ledger: dict) -> list[str]:
    """Return tracked - covered while preserving tracked order."""
    covered = set(ledger.get("covered") or [])
    return [pid for pid in tracked_pids if pid not in covered]


def filter_increment_candidates(cands: list[dict], new_pids: set[str], judged_ids: set[str]) -> list[dict]:
    """Keep rows touching a new pid and not already judged.

    ③-C candidate rows use actual keys: ``from``, ``to``, ``candidate_id``.
    """
    out = []
    for row in cands:
        if row.get("candidate_id") in judged_ids:
            continue
        if row.get("from") in new_pids or row.get("to") in new_pids:
            out.append(row)
    return out


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def check_apply_gates(out_root: Path, vault_rel_dir: Path, min_keep_ratio: float = 0.8) -> str | None:
    canonical = out_root / "relations_canonical.jsonl"
    adjacency = out_root / "_index_by_policy.json"
    ob_dir = out_root / "_index_by_policy"

    if not canonical.exists() or not adjacency.exists() or not ob_dir.is_dir():
        return "relation view preview missing canonical, adjacency, or _index_by_policy"
    new_edges = _count_jsonl_rows(canonical)
    if new_edges <= 0:
        return "relation view preview canonical is empty"
    try:
        json.loads(adjacency.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"relation view preview adjacency is not parseable JSON: {exc}"

    old_canonical = vault_rel_dir / "relations_canonical.jsonl"
    if old_canonical.exists():
        old_edges = _count_jsonl_rows(old_canonical)
        if new_edges < old_edges * min_keep_ratio:
            return f"canonical edge count collapsed: new={new_edges} old={old_edges} min_keep_ratio={min_keep_ratio}"
    return None


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def write_pid_ledger(path: Path, covered: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"covered": list(covered), "updated_at": _now_iso()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def _read_judged_ids(path: Path) -> set[str]:
    return {str(row.get("candidate_id")) for row in _iter_jsonl(path) if row.get("candidate_id")}


def _tracked_policy_pids(vault: Path) -> list[str]:
    files = hpr_run._tracked_policy_files(vault)
    docs = hpr_run._load_policy_docs(vault, files)
    return [doc.policy_id for doc in docs]


def _extract_policy_ids(root: Path) -> list[str]:
    pids = []
    for path in sorted((root / "0_raw" / "policies").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.search(r"(?m)^id:\s*['\"]?([^'\"\n#]+)", text)
        if m:
            pids.append(m.group(1).strip())
    return pids


def init_ledger(vault: Path, state_dir: Path, as_of_commit: str) -> dict:
    state_dir = Path(state_dir)
    ledger_path = state_dir / PID_LEDGER
    with tempfile.TemporaryDirectory(prefix="relations-ledger-") as tmp:
        tmp_root = Path(tmp)
        archive = subprocess.Popen(
            ["git", "-C", str(vault), "archive", as_of_commit, "0_raw/policies"],
            stdout=subprocess.PIPE,
        )
        try:
            with tarfile.open(fileobj=archive.stdout, mode="r|") as tf:
                tf.extractall(tmp_root)
        finally:
            if archive.stdout is not None:
                archive.stdout.close()
        rc = archive.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, ["git", "-C", str(vault), "archive", as_of_commit, "0_raw/policies"])
        covered = _extract_policy_ids(tmp_root)
    write_pid_ledger(ledger_path, covered)
    return {"covered": len(covered)}


def _replace_relations(out_root: Path, vault_rel_dir: Path) -> None:
    vault_rel_dir.mkdir(parents=True, exist_ok=True)
    for name in ("relations_canonical.jsonl", "_index_by_policy.json", "_index_by_policy"):
        target = vault_rel_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    shutil.copy2(out_root / "relations_canonical.jsonl", vault_rel_dir / "relations_canonical.jsonl")
    shutil.copy2(out_root / "_index_by_policy.json", vault_rel_dir / "_index_by_policy.json")
    shutil.copytree(out_root / "_index_by_policy", vault_rel_dir / "_index_by_policy")


def _build_judge_client(judge_model: str, judge_provider: str, log_path: Path):
    if judge_provider != "openai":
        raise ValueError(f"unsupported judge_provider: {judge_provider}")
    from scripts.common.llm import OpenAICompatClient

    return OpenAICompatClient(model=judge_model, log_path=str(log_path))


def run_increment(
    vault: Path,
    state_dir: Path,
    judge_model: str,
    judge_provider: str = "openai",
    *,
    dry_run: bool = False,
    judge_client=None,
) -> dict:
    vault = Path(vault)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = state_dir / PID_LEDGER
    sem_cumulative = state_dir / SEM_ACCEPTED
    judged_ledger = state_dir / JUDGED_LEDGER

    hpr_state = state_dir / "relations_increment" / "hpr"
    hpr_run.run_preview(vault, hpr_state)
    hpr_path = hpr_state / "high_precision_relation_candidates.jsonl"

    tracked_pids = _tracked_policy_pids(vault)
    ledger = _load_json(ledger_path, {"covered": []})
    new_pids = select_new_pids(tracked_pids, ledger)
    if not new_pids:
        return {"new_pids": 0}

    views = load_policy_views(vault=vault)
    basis = load_hpr_basis_pairs(hpr_path)
    candidates = [c.to_row() for c in generate_candidates(views, basis)]
    inc_candidates = filter_increment_candidates(candidates, set(new_pids), _read_judged_ids(judged_ledger))
    valid = [row for row in inc_candidates if not program_gate.check_candidate_row(row)]

    client = judge_client or _build_judge_client(judge_model, judge_provider, state_dir / "relations_increment" / "judge_calls.jsonl")
    judgments: dict[str, str] = {}
    judged_rows: list[dict] = []
    for cand in valid:
        judgment = judge_candidate(client, cand)
        judgments[cand["candidate_id"]] = judgment.decision
        cand["confidence"] = judgment.confidence
        cand["judge_reason"] = judgment.reason
        cand["model"] = judgment.model
        judged_rows.append({"candidate_id": cand["candidate_id"], "decision": judgment.decision, "ts": _now_iso()})

    accepted, _manual = program_gate.partition_by_decision(valid, judgments)
    _append_jsonl(sem_cumulative, accepted)
    _append_jsonl(judged_ledger, judged_rows)

    out_root = state_dir / "relations_increment" / "views"
    if out_root.exists():
        shutil.rmtree(out_root)
    relation_summary = run_relation_views_preview(vault, sem_cumulative, hpr_path, out_root)
    canonical_edges = int(relation_summary.get("canonical_edge_count") or 0)

    summary = {
        "new_pids": len(new_pids),
        "judged": len(judged_rows),
        "accepted": len(accepted),
        "canonical_edges": canonical_edges,
        "applied": False,
    }
    if dry_run:
        return summary

    vault_rel_dir = vault / "1_extracted" / "relations"
    reason = check_apply_gates(out_root, vault_rel_dir)
    if reason is not None:
        send_text(f"[S2] 关系增量 apply gate refused: {reason}")
        print(json.dumps({"error": reason, **summary}, ensure_ascii=False))
        raise SystemExit(1)

    _replace_relations(out_root, vault_rel_dir)
    covered = list(ledger.get("covered") or [])
    covered_set = set(covered)
    for pid in new_pids:
        if pid not in covered_set:
            covered.append(pid)
            covered_set.add(pid)
    write_pid_ledger(ledger_path, covered)
    summary["applied"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="③ 关系族增量编排器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-ledger")
    p_init.add_argument("--vault", type=Path, required=True)
    p_init.add_argument("--state-dir", type=Path, required=True)
    p_init.add_argument("--as-of-commit", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--vault", type=Path, required=True)
    p_run.add_argument("--state-dir", type=Path, required=True)
    p_run.add_argument("--judge-model", required=True)
    p_run.add_argument("--judge-provider", default="openai")
    p_run.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "init-ledger":
        result = init_ledger(args.vault, args.state_dir, args.as_of_commit)
    elif args.cmd == "run":
        result = run_increment(args.vault, args.state_dir, args.judge_model, args.judge_provider, dry_run=args.dry_run)
    else:
        raise SystemExit(f"unsupported command: {args.cmd}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
