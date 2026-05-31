"""②-A 编排:dry-run / apply / verify。"""
from __future__ import annotations
import argparse
import json
import datetime
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.l2_attribution.channel_registry import load_registry
from scripts.l2_attribution.ledger import load_ledger, cross_check
from scripts.l2_attribution.resolver import resolve_identity, body_tail_of
from scripts.l2_attribution.apply_identity import apply_identity
from scripts.l2_attribution.review_queue import write_queue
from scripts.l2_attribution import report

DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")


def _existing_ids(recs):
    return {r.pid for r in recs if r.pid}


def plan(policies_dir, registry_path, ledger_path):
    recs = load_policies(policies_dir)
    registry = load_registry(registry_path)
    ledger = load_ledger(ledger_path) if Path(ledger_path).exists() else {}
    existing = _existing_ids(recs)
    to_apply, queue = [], []
    for rec in recs:
        ri = resolve_identity(rec, registry, body_tail_of(rec.path), existing)
        if "id" in ri.fields and rec.pid in ledger:
            status, detail = cross_check(ri.fields["id"].value, ledger[rec.pid])
            if status == "disagree":
                ri.fields = {}
                ri.add_conflict("_all", reason="与 ledger 矛盾(保守不写)", signals=detail)
        if ri.has_conflicts() and not ri.fields:
            queue.append(ri)
        elif ri.fields:
            to_apply.append(ri)
            if ri.has_conflicts():
                queue.append(ri)
        else:
            pass  # no-op
    return to_apply, queue


def _agree_rate(to_apply, ledger):
    pairs = [(ri, ledger[ri.pid]) for ri in to_apply
             if "id" in ri.fields and ri.pid in ledger]
    if not pairs:
        return 1.0
    ok = sum(1 for ri, le in pairs if cross_check(ri.fields["id"].value, le)[0] == "agree")
    return ok / len(pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dry-run", "apply", "verify"])
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--state", default="state/source_ready")
    args = ap.parse_args()

    pol = f"{args.vault}/0_raw/policies"
    reg = f"{args.vault}/_meta/channel_registry.yaml"
    led = f"{args.state}/attribution_ledger_2b.jsonl"
    Path(args.state).mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    to_apply, queue = plan(pol, reg, led)
    ledger = load_ledger(led) if Path(led).exists() else {}
    rate = _agree_rate(to_apply, ledger)

    if args.mode == "dry-run":
        with open(f"{args.state}/proposed_changes_2a.jsonl", "w", encoding="utf-8") as f:
            for ri in to_apply:
                f.write(json.dumps(
                    {"pid": ri.pid,
                     "fields": {k: v.value for k, v in ri.fields.items()}},
                    ensure_ascii=False) + "\n")
        write_queue(queue, f"{args.state}/2a_review_queue.jsonl")
        report.render(to_apply, queue, rate, f"{args.state}/2a_dryrun_report.html")
        print(f"dry-run: 将写 {len(to_apply)} 篇,入队 {len(queue)} 篇,ledger一致率 {rate:.1%}")
        print(f"报告: {args.state}/2a_dryrun_report.html")

    elif args.mode == "apply":
        assert rate >= 0.95, f"ledger 一致率 {rate:.1%} < 95%,验收门不过,拒绝 apply"
        log = []
        recs_by_pid = {r.pid: r.path for r in load_policies(pol)}
        for ri in to_apply:
            written = apply_identity(recs_by_pid[ri.pid], ri, fixed_at=now)
            log.append({"pid": ri.pid, "written": written, "at": now})
        with open(f"{args.state}/apply_log_2a.jsonl", "w", encoding="utf-8") as f:
            for e in log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"apply: 写了 {len(log)} 篇。请在 vault 仓 commit(git status 看改动)。")

    elif args.mode == "verify":
        again, _ = plan(pol, reg, led)
        print(f"verify: 幂等重跑待写 {len(again)} 篇(应为 0);ledger一致率 {rate:.1%}")
        assert len(again) == 0, "非幂等:apply 后仍有待写,检查 resolver"


if __name__ == "__main__":
    main()
