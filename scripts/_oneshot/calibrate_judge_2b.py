#!/usr/bin/env python3
"""②-B Task13: run judge against frozen golden_v1 and render calibration report."""
import argparse
import html
import json
import time
from pathlib import Path

from scripts.common.llm import LLMClient, OpenAICompatClient
from scripts.l1_audit.corpus import load_policies
from scripts.l2_themescore.generator import parse_json_block
from scripts.l2_themescore.golden import score_judge
from scripts.l2_themescore.models import BusinessViewDraft, JudgeVerdict, Scores


DEFAULT_VAULT = str(Path.home() / "Documents" / "Zayn Main" / "政策分析")
DEFAULT_GOLDEN = "state/node2b/golden/golden_v1.jsonl"
DEFAULT_OUT = "state/node2b/reports"


def make_client(provider, model, log_path):
    if provider == "openai":
        return OpenAICompatClient(model=model, log_path=log_path)
    return LLMClient(model=model, log_path=log_path)


def read_golden(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def read_existing(path):
    if not Path(path).exists():
        return {}
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "record_id" in row:
            out[row["record_id"]] = row
    return out


def to_draft(rec):
    return BusinessViewDraft(
        pid=rec["pid"],
        themes=rec.get("themes", rec.get("gold_themes", [])),
        primary_theme=rec.get("primary_theme", rec.get("gold_primary", "")),
        comprehensive=bool(rec.get("comprehensive", False)),
        scores=Scores.from_dict(rec.get("scores", rec.get("gold_scores", {}))),
        importance=rec.get("importance"),
        影响分析=rec.get("影响分析", rec.get("gold_影响分析")),
    )


CALIBRATION_JUDGE_SYSTEM = """你是独立第三方审查员,审查另一模型给政策做的归属(theme+分+影响分析)。
本次是 golden 校准:clean gold 只冻结了 themes/primary/scores/comprehensive;部分 clean 样本的影响分析为 null。
规则:
1. 只能在既定的 13 个滴滴业务主题内审: v2g, vpp_theme, energy_storage_theme,
   gas_station_transition_theme, equipment_renewal_theme, green_power_trading_theme,
   charging_infra, power_market, carbon_market_theme, petroleum_retail_compliance,
   residential_charging, distribution_grid_opening, aggregator_access。
   不得发明"新能源发展/光伏项目管理/产业规划/企业治理/资源节约"等外部主题来判漏挂。
2. 零主题可以成立:若政策只属于 13 个滴滴业务主题以外的泛能源、产业、目录、历史管理、
   企业治理、资源节约等内容, themes=[]/primary="" 应 accept,不得因外部主题存在而 reject。
3. theme 审查只抓明显业务主题错:把不相关政策挂到 13 主题、漏掉正文明确且重要的 13 主题、
   primary 与 13 主题主旨明显颠倒、comprehensive 明显错。边界争议默认 accept。
   具体地,以下情况不要 reject:
   - 历史政策或早期政策中出现了电力市场/需求响应/调峰/输配电价等机制雏形,挂 power_market、vpp_theme、
     energy_storage_theme、green_power_trading_theme 等相邻 13 主题只要有文本依据即可 accept。
   - 综合/宏观政策覆盖多个产业或能源方向时,只要命中的 13 主题是正文中的明确子机制,即使不是全文唯一中心也 accept。
   - 辅助主题是否应挂、primary 在几个相关 13 主题之间如何排序,属于边界争议;除非与正文主旨完全相反,否则 accept。
   - D4/D5/D6 或非 D1/D2 的分数争议不作为 reject;只有 D1/D2 明显颠倒到影响重要性判断时才 reject。
4. 若影响分析为 null,不得因为"缺少影响分析"而 reject;只审 theme/primary/comprehensive/scores 是否有明显语义错。
5. 若影响分析非 null,要审是否对零相关政策硬写、是否明显幻觉。
6. 对 13 主题内部的明显错误要严格 reject,不要因"已有一个正确主题"就 accept:
   以下严重错优先级高于"边界争议默认 accept",命中任一条就 reject:
   - 政策条款明确写出"虚拟电厂/负荷聚合商/聚合商/车网互动/参与电力市场",但 themes 只留下 energy_storage_theme 或只留下 v2g = 漏挂, reject。
   - 政策明确覆盖 5 个以上 13 主题且无单一中心,若 comprehensive=false 或 primary 被硬塞成 charging_infra/v2g 等窄主题 = reject。
   - 对直接部署电动汽车充电基础设施、车网互动试点、国家级电力交易基础规则的政策,若 D1 或 D2 被压到 2 以下 = 明显低估, reject。
   - 只讲碳排放权交易的政策,不得因"交易"二字挂 power_market/green_power_trading_theme;除非正文明确电力市场或绿证/绿电交易机制,否则 reject。
   - 居民阶梯电价、光伏项目建设管理、政府目录索引等不属于 13 主题的零相关/弱相关政策,若被挂上 power_market/green_power_trading_theme/charging_infra 并抬到重要性≥3 = reject。
   - 零相关政策若写出具体充电/储能/V2G业务影响 = impact 幻觉, reject。
只输出 JSON:{"verdict":"accept|reject","dim":"theme|score|impact|overall","reason":"一句话","confidence":0-1}
"""


def judge_calibration_draft(client, rec_title: str, rec_body: str, draft) -> JudgeVerdict:
    user = (f"政策标题:{rec_title}\n正文(节选):\n{rec_body[:1500]}\n\n"
            f"待审归属:themes={draft.themes} primary={draft.primary_theme} "
            f"comprehensive={draft.comprehensive} scores={draft.scores.to_dict()} "
            f"重要性={draft.importance} 影响分析={draft.影响分析}")
    txt = client.complete(system=CALIBRATION_JUDGE_SYSTEM, user=user, max_tokens=1024)
    try:
        d = parse_json_block(txt)
    except Exception:
        return JudgeVerdict(verdict="reject", dim="overall",
                            reason="judge 返回非JSON", confidence=0.0)
    return JudgeVerdict(verdict=d.get("verdict", "reject"), dim=d.get("dim", "overall"),
                        reason=d.get("reason", ""), confidence=float(d.get("confidence", 0.0)))


def esc(s):
    return html.escape(str(s if s is not None else ""))


def render_html(rows, summary, path):
    trs = []
    for r in rows:
        cls = "ok" if r["correct"] else "bad"
        trs.append(f"""<tr class="{cls}">
<td>{esc(r['pid'])}<br><small>{esc(r.get('error_type') or '')}</small></td>
<td>{'planted' if r['is_planted'] else 'clean'}</td>
<td>{esc(r['expected'])}</td>
<td>{esc(r['verdict'])}</td>
<td>{esc(r['dim'])}<br><small>{esc(r['confidence'])}</small></td>
<td>{esc(r['reason'])}</td>
</tr>""")
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>②-B judge 校准</title>
<style>
body{{font:14px/1.55 -apple-system,"PingFang SC",sans-serif;margin:0;background:#f6f8fb;color:#1c2530}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 18px 60px}}
h1{{font-size:22px;margin:0 0 12px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 18px}}
.stat{{background:#fff;border:1px solid #e1e6ee;border-radius:8px;padding:10px 14px}}
.stat b{{font-size:22px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e1e6ee;border-radius:8px;overflow:hidden}}
th,td{{padding:8px 10px;border-bottom:1px solid #eef1f4;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#edf2f7;color:#526071}}
tr.ok td{{background:#f2fbf5}} tr.bad td{{background:#fff1f1}}
small{{color:#697589}}
</style></head><body><div class="wrap">
<h1>②-B judge 校准</h1>
<div class="stats">
<div class="stat">召回<br><b>{summary['recall']:.3f}</b></div>
<div class="stat">精度<br><b>{summary['precision']:.3f}</b></div>
<div class="stat">clean<br><b>{summary['n_clean']}</b></div>
<div class="stat">planted<br><b>{summary['n_planted']}</b></div>
<div class="stat">reject<br><b>{summary['n_rejected']}</b></div>
</div>
<table><tr><th>pid</th><th>类型</th><th>期望</th><th>judge</th><th>维度/置信</th><th>理由</th></tr>
{''.join(trs)}
</table></div></body></html>"""
    Path(path).write_text(doc, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--judge-provider", default="openai", choices=["anthropic", "openai"])
    ap.add_argument("--judge-model", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = make_client(args.judge_provider, args.judge_model, str(out_dir / "judge_calibration_calls.jsonl"))
    policies = {p.pid: p for p in load_policies(f"{args.vault}/0_raw/policies")}
    results_path = out_dir / "judge_calibration.jsonl"
    existing = read_existing(results_path)

    rows = []
    for rec in read_golden(args.golden):
        record_id = rec.get("record_id", rec["pid"])
        if record_id in existing:
            rows.append(existing[record_id])
            print(f"{len(rows):02d} {record_id}: reused {existing[record_id]['verdict']}", flush=True)
            continue
        policy = policies.get(rec["pid"])
        title = (policy.title if policy else rec.get("title", rec["pid"]))
        body = (policy.body_head if policy else "")
        for attempt in range(2):
            try:
                verdict = judge_calibration_draft(client, title, body, to_draft(rec))
                break
            except Exception:
                if attempt == 1:
                    raise
                time.sleep(2)
        expected = "reject" if rec.get("is_planted") else "accept"
        row = {
            "pid": rec["pid"],
            "record_id": record_id,
            "is_planted": bool(rec.get("is_planted")),
            "error_type": rec.get("error_type"),
            "expected": expected,
            "verdict": verdict.verdict,
            "dim": verdict.dim,
            "reason": verdict.reason,
            "confidence": verdict.confidence,
            "correct": verdict.verdict == expected,
        }
        rows.append(row)
        with open(results_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{len(rows):02d} {record_id}: expected={expected} got={verdict.verdict} {verdict.dim} {verdict.confidence}", flush=True)

    summary = score_judge([(r["record_id"], r["verdict"], r["is_planted"]) for r in rows])
    summary["n_clean"] = sum(1 for r in rows if not r["is_planted"])
    with open(results_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps({"_summary": summary}, ensure_ascii=False) + "\n")
    html_path = out_dir / "judge_calibration.html"
    render_html(rows, summary, html_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report: {html_path}")


if __name__ == "__main__":
    main()
