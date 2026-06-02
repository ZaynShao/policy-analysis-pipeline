import argparse, html, json
from pathlib import Path
from scripts.l1_audit.corpus import load_policies
from scripts.common.llm import LLMClient, OpenAICompatClient
from .theme_registry import ThemeRegistry, canonical_theme_id, canonicalize_theme_ids
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

def _draft_row(d):
    return {"pid": d.pid, "themes": d.themes, "primary": d.primary_theme,
            "重要性": d.importance, "gate": d.gate_passed_deep}

def _draft_full_row(d):
    return {
        "pid": d.pid,
        "themes": list(d.themes or []),
        "primary_theme": d.primary_theme,
        "comprehensive": bool(d.comprehensive),
        "scores": d.scores.to_dict(),
        "重要性": d.importance,
        "行动分类": d.action_class,
        "价值标签": list(d.value_tags or []),
        "gate_passed_deep": bool(d.gate_passed_deep),
        "影响分析": d.影响分析,
        "行动建议": list(d.行动建议 or []),
        "didi_impact_one_liner": d.didi_impact_one_liner,
    }

def _draft_from_full_row(row: dict) -> BusinessViewDraft:
    return BusinessViewDraft(
        pid=row["pid"],
        themes=row.get("themes", []),
        primary_theme=row.get("primary_theme", ""),
        comprehensive=bool(row.get("comprehensive", False)),
        scores=Scores.from_dict(row["scores"]),
        importance=row.get("重要性"),
        action_class=row.get("行动分类"),
        value_tags=row.get("价值标签", []),
        gate_passed_deep=bool(row.get("gate_passed_deep", False)),
        影响分析=row.get("影响分析"),
        行动建议=row.get("行动建议", []),
        didi_impact_one_liner=row.get("didi_impact_one_liner"),
    )

def load_drafts_full(state: str) -> list:
    path = Path(state) / "proposed_changes" / "drafts_full.jsonl"
    return [_draft_from_full_row(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]

def load_preview_drafts(state: str) -> tuple:
    full_path = Path(state) / "proposed_changes" / "drafts_full.jsonl"
    if full_path.exists():
        return load_drafts_full(state), True
    summary_path = Path(state) / "proposed_changes" / "drafts.jsonl"
    drafts = []
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        drafts.append(BusinessViewDraft(
            pid=row["pid"],
            themes=row.get("themes", []),
            primary_theme=row.get("primary", ""),
            scores=Scores(0, 0, 0, 0, 0, 0),
            importance=row.get("重要性"),
            gate_passed_deep=bool(row.get("gate", False)),
        ))
    return drafts, False

def load_queue_records(state: str) -> list:
    path = Path(state) / "review_queue" / "queue.jsonl"
    if not path.exists():
        return []
    return [QueueRecord(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]

def render_apply_preview(drafts: list, queue: list, out_path: str, full_available: bool = True) -> str:
    def esc(x): return html.escape(str(x))
    draft_rows = "".join(
        f"<tr><td>{esc(d.pid)}</td><td>{esc(', '.join(d.themes or []))}</td>"
        f"<td>{esc(d.primary_theme)}</td><td>{esc(d.importance)}</td></tr>"
        for d in drafts)
    queue_rows = "".join(
        f"<tr><td>{esc(q.pid)}</td><td>{esc(q.stage)}</td><td>{esc(q.reason)}</td></tr>"
        for q in queue)
    full_note = ("完整 accepted draft 可用,可作为离线 apply 输入。"
                 if full_available else
                 "仅找到旧版 drafts.jsonl 简表,可预览名单,但不能直接离线 apply;需重新 dry-run 生成 drafts_full.jsonl。")
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>离线 apply 预览</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;line-height:1.55;color:#1f2937;background:#f8fafc}}
section{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px;margin:18px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #e5e7eb;padding:7px 8px;vertical-align:top}} th{{background:#f1f5f9;text-align:left}}
.num{{font-size:28px;font-weight:700;color:#0f766e}} .note{{color:#475569}}
</style></head><body>
<h1>离线 apply 预览</h1>
<p class="note">来源: dry-run 的 drafts_full.jsonl / queue.jsonl。此报告不会调用模型,也不会写入业务库。</p>
<p class="note">{esc(full_note)}</p>
<section><h2>概览</h2><p>将写入 <span class="num">{len(drafts)}</span> 篇; 仍入队 <span class="num">{len(queue)}</span> 篇。</p></section>
<section><h2>将写入</h2><table><tr><th>PID</th><th>Themes</th><th>Primary</th><th>重要性</th></tr>{draft_rows}</table></section>
<section><h2>仍入队</h2><table><tr><th>PID</th><th>阶段</th><th>原因</th></tr>{queue_rows}</table></section>
</body></html>"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(doc, encoding="utf-8")
    return out_path

def verify_drafts(drafts: list, registry_path: str) -> list:
    reg = ThemeRegistry.load(registry_path)
    failures = []
    for draft in drafts:
        viol = program_gate.check_draft(draft, reg.ids)
        if viol:
            failures.append((draft.pid, viol))
    return failures

def apply_accepted_drafts(vault: str, drafts: list, extracted_at: str, extracted_model: str,
                          registry_path: str = None) -> list:
    if registry_path:
        failures = verify_drafts(drafts, registry_path)
        if failures:
            raise ValueError(f"accepted draft scoped verify 失败: {len(failures)} 篇")
    rec_by_pid = {rec.pid: rec for rec in load_policies(f"{vault}/0_raw/policies")}
    written = []
    for draft in drafts:
        rec = rec_by_pid.get(draft.pid)
        if rec is None:
            raise ValueError(f"accepted draft 找不到原始政策: {draft.pid}")
        written.append(write_business_view(
            draft, vault,
            sanitized_from="0_raw/policies/" + Path(rec.path).name,
            extracted_at=extracted_at,
            extracted_model=extracted_model,
        ))
    return written

def _append_jsonl(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def _dryrun_item_writer(state: str):
    drafts_path = Path(state) / "proposed_changes" / "drafts.jsonl"
    drafts_full_path = Path(state) / "proposed_changes" / "drafts_full.jsonl"
    queue_path = Path(state) / "review_queue" / "queue.jsonl"
    drafts_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    drafts_path.write_text("", encoding="utf-8")
    drafts_full_path.write_text("", encoding="utf-8")
    queue_path.write_text("", encoding="utf-8")
    def write_item(event):
        kind, item = event
        if kind == "draft":
            _append_jsonl(drafts_path, _draft_row(item))
            _append_jsonl(drafts_full_path, _draft_full_row(item))
        elif kind == "queue":
            _append_jsonl(queue_path, item.to_dict())
    return write_item

def _contains_any(text: str, keywords: tuple) -> bool:
    return any(k in text for k in keywords)

def _remove_theme(draft: BusinessViewDraft, theme: str):
    if theme in (draft.themes or []):
        draft.themes = [t for t in draft.themes if t != theme]
        if draft.primary_theme == theme:
            draft.primary_theme = draft.themes[0] if draft.themes else ""

def _normalize_theme_evidence(rec, draft: BusinessViewDraft):
    """Global deterministic evidence cleanup. Removes unsupported over-expansion and
    stabilizes primary when an explicit charging buildout is embedded in a grid plan."""
    text = rec.body_head or ""
    residential_evidence = _contains_any(text, (
        "居民小区", "居住区", "住宅小区", "老旧小区", "居民区", "停车位电气化",
        "居民充电", "私人充电", "社区充电",
    ))
    equipment_evidence = _contains_any(text, (
        "设备更新", "大规模设备更新", "以旧换新", "消费品以旧换新", "标准提升",
        "更新换新", "淘汰更新",
    ))
    storage_evidence = _contains_any(text, (
        "新型储能", "储能电站", "储能项目", "储能设施", "用户侧储能", "独立储能",
        "储能参与", "储能产业", "光储充", "光储充换", "储能系统", "调频辅助服务",
    ))
    charging_buildout = _contains_any(text, (
        "充电基础设施建设", "充电设施全覆盖", "充换电设施", "充换电基础设施",
        "桩车比", "为充电设施预留配电房", "停车位电气化改造",
    ))
    if not residential_evidence:
        _remove_theme(draft, "residential_charging")
    if not equipment_evidence:
        _remove_theme(draft, "equipment_renewal_theme")
    if not storage_evidence:
        _remove_theme(draft, "energy_storage_theme")
    if charging_buildout and "charging_infra" in (draft.themes or []):
        draft.primary_theme = "charging_infra"
    return draft

def _normalize_pass2_payload(o2: dict):
    impact = dict(o2.get("影响分析") or {})
    actions = o2.get("行动建议", [])
    one_liner = o2.get("didi_impact_one_liner")
    nested_actions = impact.pop("行动建议", None)
    nested_one_liner = impact.pop("didi_impact_one_liner", None)
    if not actions and nested_actions is not None:
        actions = nested_actions
    if not one_liner and nested_one_liner is not None:
        one_liner = nested_one_liner
    return impact, actions, one_liner

def plan(vault, registry_path, scoring_text, gen_client, judge_client, gen_pass2_client=None, include_pids=None, on_item=None):
    gen_pass2_client = gen_pass2_client or gen_client
    reg = ThemeRegistry.load(registry_path)
    recs = load_policies(f"{vault}/0_raw/policies")
    if include_pids is not None:
        recs = [rec for rec in recs if rec.pid in include_pids]
    p1_sys = prompts.pass1_system(reg, scoring_text)
    p2_sys = prompts.pass2_system()
    to_write, queue = [], []
    for rec in recs:
        try:
            o1 = gen_pass1(gen_client, p1_sys, prompts.pass1_user(rec))
            draft = BusinessViewDraft(
                pid=rec.pid, themes=canonicalize_theme_ids(o1.get("themes", []), reg.ids),
                primary_theme=canonical_theme_id(o1.get("primary_theme",""), reg.ids),
                comprehensive=bool(o1.get("comprehensive", False)),
                scores=Scores.from_dict(o1["scores"]))
            _normalize_theme_evidence(rec, draft)
        except Exception as e:
            qr = QueueRecord(pid=rec.pid, stage="generation_error", reason=str(e)[:200])
            queue.append(qr)
            if on_item:
                on_item(("queue", qr))
            continue
        draft.importance = scoring.importance(draft.scores)
        draft.action_class = scoring.action_class(draft.scores)
        draft.value_tags = scoring.value_tags(draft.importance, draft.themes)
        region_level = (rec.raw_fm.get("region") or {}).get("level", "")
        draft.gate_passed_deep = bool(draft.themes) and scoring.gate_passed_deep(draft.importance, region_level)
        if draft.gate_passed_deep:
            try:
                o2 = gen_pass2(gen_pass2_client, p2_sys, prompts.pass2_user(rec, draft))
                draft.影响分析, draft.行动建议, draft.didi_impact_one_liner = _normalize_pass2_payload(o2)
            except Exception as e:
                qr = QueueRecord(pid=rec.pid, stage="generation_error", reason=f"pass2:{e}"[:200])
                queue.append(qr)
                if on_item:
                    on_item(("queue", qr))
                continue
        viol = program_gate.check_draft(draft, reg.ids)
        if viol:
            qr = QueueRecord(pid=rec.pid, stage="program_gate", reason="; ".join(viol))
            queue.append(qr)
            if on_item:
                on_item(("queue", qr))
            continue
        v = judge_draft(judge_client, rec.title, rec.body_head, draft)
        if v.verdict != "accept":
            qr = QueueRecord(pid=rec.pid, stage="judge_reject", reason=v.reason,
                             detail={"dim": v.dim, "confidence": v.confidence})
            queue.append(qr)
            if on_item:
                on_item(("queue", qr))
            continue
        to_write.append((rec, draft))
        if on_item:
            on_item(("draft", draft))
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
    ap.add_argument("mode", choices=["dry-run", "apply", "verify", "preview-accepted", "apply-accepted"])
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--state", default="state/node2b")
    ap.add_argument("--gen-model")
    ap.add_argument("--judge-model")
    ap.add_argument("--gen-provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--judge-provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--pid-file", help="JSON array or newline-delimited pid list for bounded dry-runs")
    args = ap.parse_args()

    reg_path = f"{args.vault}/_meta/themes_registry.yaml"

    if args.mode == "preview-accepted":
        drafts, full_available = load_preview_drafts(args.state)
        queue = load_queue_records(args.state)
        out = render_apply_preview(drafts, queue, f"{args.state}/reports/apply_preview.html",
                                   full_available=full_available)
        print(f"preview-accepted: 将写 {len(drafts)} · 仍入队 {len(queue)} · 报告 {out}")
        return

    if args.mode == "apply-accepted":
        if not args.gen_model:
            raise SystemExit("apply-accepted 需要 --gen-model 作为 extracted_model 元数据;不会调用模型")
        from datetime import date
        drafts = load_drafts_full(args.state)
        queue = load_queue_records(args.state)
        written = apply_accepted_drafts(args.vault, drafts, extracted_at=date.today().isoformat(),
                                        extracted_model=args.gen_model, registry_path=reg_path)
        out = render_apply_preview(drafts, queue, f"{args.state}/reports/apply_accepted.html")
        failures = verify_drafts(drafts, reg_path)
        if failures:
            raise SystemExit(f"apply-accepted 写入后 scoped verify 失败: {len(failures)} 篇")
        print(f"apply-accepted: 写 business_view {len(written)} 篇 · 仍入队 {len(queue)} · verify 通过 · 报告 {out}")
        return

    if args.mode in {"dry-run", "apply"}:
        if not args.gen_model or not args.judge_model:
            raise SystemExit(f"{args.mode} 需要 --gen-model 和 --judge-model")
        assert args.gen_model != args.judge_model, "judge 模型必须 ≠ generator 模型"

    sc_text = _scoring_text(args.vault)
    gen_client = make_client(args.gen_provider, args.gen_model, f"{args.state}/gen_calls.jsonl")
    judge_client = make_client(args.judge_provider, args.judge_model, f"{args.state}/judge_calls.jsonl")
    include_pids = None
    if args.pid_file:
        text = Path(args.pid_file).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
            include_pids = set(data if isinstance(data, list) else data.get("pids", []))
        except json.JSONDecodeError:
            include_pids = {line.strip() for line in text.splitlines() if line.strip()}

    on_item = _dryrun_item_writer(args.state) if args.mode == "dry-run" else None
    to_write, queue = plan(args.vault, reg_path, sc_text, gen_client, judge_client,
                           include_pids=include_pids, on_item=on_item)
    drafts = [d for _, d in to_write]
    warns = program_gate.check_distribution(drafts, len(ThemeRegistry.load(reg_path).ids))

    if args.mode == "dry-run":
        Path(f"{args.state}/proposed_changes").mkdir(parents=True, exist_ok=True)
        with open(f"{args.state}/proposed_changes/drafts.jsonl", "w", encoding="utf-8") as f:
            for rec, d in to_write:
                f.write(json.dumps(_draft_row(d), ensure_ascii=False) + "\n")
        with open(f"{args.state}/proposed_changes/drafts_full.jsonl", "w", encoding="utf-8") as f:
            for rec, d in to_write:
                f.write(json.dumps(_draft_full_row(d), ensure_ascii=False) + "\n")
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
