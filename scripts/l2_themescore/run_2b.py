import argparse, json
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.common.llm import LLMClient, OpenAICompatClient
from .theme_registry import ThemeRegistry
from .models import BusinessViewDraft, Scores, QueueRecord
from . import scoring, program_gate, prompts
from .generator import gen_pass1, gen_pass2
from .judge import judge_draft
from .business_view_writer import write_business_view
from .review_queue import write_queue
from . import report

DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")
DEFAULT_SCORING = "_meta/framework/scoring.yaml"

def _scoring_text(vault) -> str:
    return Path(f"{vault}/{DEFAULT_SCORING}").read_text(encoding="utf-8")

def make_client(provider: str, model: str, log_path: str):
    """provider=anthropic → LLMClient(读 ANTHROPIC_*,如 Claude / MiniMax 兼容端点);
    provider=openai → OpenAICompatClient(读 OPENAI_*,如 DashScope/Qwen)。gen 与 judge 各自独立端点。"""
    if provider == "openai":
        return OpenAICompatClient(model=model, log_path=log_path)
    return LLMClient(model=model, log_path=log_path)

def plan(vault, registry_path, scoring_text, gen_client, judge_client, gen_pass2_client=None):
    gen_pass2_client = gen_pass2_client or gen_client
    reg = ThemeRegistry.load(registry_path)
    recs = load_policies(f"{vault}/0_raw/policies")
    p1_sys = prompts.pass1_system(reg, scoring_text)
    p2_sys = prompts.pass2_system()
    to_write, queue = [], []
    for rec in recs:
        try:
            o1 = gen_pass1(gen_client, p1_sys, prompts.pass1_user(rec))
            draft = BusinessViewDraft(
                pid=rec.pid, themes=o1.get("themes", []), primary_theme=o1.get("primary_theme",""),
                scores=Scores.from_dict(o1["scores"]))
        except Exception as e:
            queue.append(QueueRecord(pid=rec.pid, stage="generation_error", reason=str(e)[:200]))
            continue
        draft.importance = scoring.importance(draft.scores)
        draft.action_class = scoring.action_class(draft.scores)
        draft.value_tags = scoring.value_tags(draft.importance, draft.themes)
        region_level = (rec.raw_fm.get("region") or {}).get("level", "")
        draft.gate_passed_deep = scoring.gate_passed_deep(draft.importance, region_level)
        if draft.gate_passed_deep:
            try:
                o2 = gen_pass2(gen_pass2_client, p2_sys, prompts.pass2_user(rec, draft))
                draft.影响分析 = o2.get("影响分析"); draft.行动建议 = o2.get("行动建议", [])
                draft.didi_impact_one_liner = o2.get("didi_impact_one_liner")
            except Exception as e:
                queue.append(QueueRecord(pid=rec.pid, stage="generation_error", reason=f"pass2:{e}"[:200]))
                continue
        viol = program_gate.check_draft(draft, reg.ids)
        if viol:
            queue.append(QueueRecord(pid=rec.pid, stage="program_gate", reason="; ".join(viol)))
            continue
        v = judge_draft(judge_client, rec.title, rec.body_head, draft)
        if v.verdict != "accept":
            queue.append(QueueRecord(pid=rec.pid, stage="judge_reject", reason=v.reason,
                                     detail={"dim": v.dim, "confidence": v.confidence}))
            continue
        to_write.append((rec, draft))
    return to_write, queue

def verify_artifacts(vault, registry_path) -> list:
    """重跑确定性层(scoring+program_gate)against 已写 business_view,断言仍自洽。不调 LLM。
    返回 list[(pid, violations)];空=全过。"""
    import yaml as _yaml
    reg = ThemeRegistry.load(registry_path)
    bv_dir = Path(vault) / "_meta" / "business_view"
    failures = []
    for p in sorted(bv_dir.glob("*.yaml")):
        doc = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        draft = BusinessViewDraft(
            pid=doc.get("pid", p.stem),
            themes=doc.get("themes", []),
            primary_theme=doc.get("primary_theme", ""),
            scores=Scores.from_dict(doc["scores"]),
            importance=doc.get("重要性"),
            action_class=doc.get("行动分类"),
            value_tags=doc.get("价值标签", []),
            gate_passed_deep=bool(doc.get("gate_passed_deep", False)),
            影响分析=doc.get("影响分析"),
            行动建议=doc.get("行动建议", []),
        )
        viol = program_gate.check_draft(draft, reg.ids)
        if viol:
            failures.append((draft.pid, viol))
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dry-run", "apply", "verify"])
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--state", default="state/node2b")
    ap.add_argument("--gen-model", required=True)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--gen-provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--judge-provider", default="anthropic", choices=["anthropic", "openai"])
    args = ap.parse_args()
    assert args.gen_model != args.judge_model, "judge 模型必须 ≠ generator 模型"

    reg_path = f"{args.vault}/_meta/themes_registry.yaml"
    sc_text = _scoring_text(args.vault)
    gen_client = make_client(args.gen_provider, args.gen_model, f"{args.state}/gen_calls.jsonl")
    judge_client = make_client(args.judge_provider, args.judge_model, f"{args.state}/judge_calls.jsonl")

    to_write, queue = plan(args.vault, reg_path, sc_text, gen_client, judge_client)
    drafts = [d for _, d in to_write]
    warns = program_gate.check_distribution(drafts, len(ThemeRegistry.load(reg_path).ids))

    if args.mode == "dry-run":
        Path(f"{args.state}/proposed_changes").mkdir(parents=True, exist_ok=True)
        with open(f"{args.state}/proposed_changes/drafts.jsonl", "w", encoding="utf-8") as f:
            for rec, d in to_write:
                f.write(json.dumps({"pid": d.pid, "themes": d.themes, "primary": d.primary_theme,
                                    "重要性": d.importance, "gate": d.gate_passed_deep},
                                   ensure_ascii=False) + "\n")
        write_queue(queue, f"{args.state}/review_queue/queue.jsonl")
        report.render(drafts, queue, warns, None, f"{args.state}/reports/dryrun.html")
        print(f"dry-run: 待写 {len(to_write)} · 入队 {len(queue)} · 告警 {len(warns)}")

    elif args.mode == "apply":
        from datetime import date
        today = date.today().isoformat()
        for rec, d in to_write:
            write_business_view(d, args.vault, sanitized_from="0_raw/policies/" + Path(rec.path).name,
                                extracted_at=today, extracted_model=args.gen_model)
        write_queue(queue, f"{args.state}/review_queue/queue.jsonl")
        report.render(drafts, queue, warns, None, f"{args.state}/reports/apply.html")
        for w in warns:
            print("WARN:", w)
        print(f"apply: 写 business_view {len(to_write)} 篇 · 入队 {len(queue)}")

    elif args.mode == "verify":
        failures = verify_artifacts(args.vault, reg_path)
        if failures:
            for pid, viol in failures[:20]:
                print(f"VERIFY FAIL {pid}: {'; '.join(viol)}")
            raise SystemExit(f"verify: {len(failures)} 篇 business_view 不过确定性门")
        n = len(list((Path(args.vault) / '_meta' / 'business_view').glob('*.yaml')))
        print(f"verify: {n} 篇 business_view 全部通过确定性重算门(自洽)")

if __name__ == "__main__":
    main()
