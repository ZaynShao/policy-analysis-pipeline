#!/usr/bin/env python3
"""③-C Task9: run restricted-relation judge against frozen golden_v1 and render calibration report.

Bar: planted_recall >= 0.9 ("没考过的 judge 不上岗").

Mirror of calibrate_judge_2b.py, adapted for relation candidates.
Calibration input == production judge input (titles + body windows from golden rows).
"""
import argparse
import html
import json
import time
from pathlib import Path

from scripts.common.llm import LLMClient, OpenAICompatClient
from scripts.analysis_semantic_relations.judge import judge_candidate


DEFAULT_GOLDEN = "state/node3c/golden/golden_v1.jsonl"
DEFAULT_OUT = "state/node3c/reports_judge"


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
        if "candidate_id" in row:
            out[row["candidate_id"]] = row
    return out


def row_to_candidate(row: dict) -> dict:
    """Reconstruct the candidate dict the judge expects from a golden row.

    Golden rows carry titles + body windows directly, so no raw policy load
    is needed: calibration input == production judge input.
    """
    cid = f'{row["from"]}|{row["to"]}|{row["rel"]}'
    return {
        "candidate_id": cid,
        "from": row["from"],
        "to": row["to"],
        "rel": row["rel"],
        "candidate_basis": row.get("candidate_basis", []),
        "evidence": {
            "from_title": row.get("from_title", ""),
            "to_title": row.get("to_title", ""),
            "from_window": row.get("from_window", ""),
            "to_window": row.get("to_window", ""),
            "theme_context": [],
        },
    }


def score_calibration(rows: list) -> dict:
    """Pure scoring function — testable without I/O.

    Each row must have: is_planted (bool), gold_decision (str), verdict (str).
    - planted rows: correct == judge did NOT accept (reject or manual_review).
    - real rows: correct == judge decision == gold_decision.

    Returns dict with planted_recall, n_planted, n_planted_caught, n_real,
    real_accept_kept, agreement, bar_pass, n_total.
    """
    planted = [r for r in rows if r["is_planted"]]
    real = [r for r in rows if not r["is_planted"]]

    n_planted = len(planted)
    n_planted_caught = sum(1 for r in planted if r["verdict"] != "accept")
    planted_recall = n_planted_caught / n_planted if n_planted else 0.0

    n_real = len(real)
    real_gold_accept = [r for r in real if r.get("gold_decision") == "accept"]
    real_accept_kept = (
        sum(1 for r in real_gold_accept if r["verdict"] == "accept") / len(real_gold_accept)
        if real_gold_accept else 1.0
    )
    agreement = (
        sum(1 for r in real if r["verdict"] == r.get("gold_decision")) / n_real
        if n_real else 1.0
    )

    return {
        "planted_recall": round(planted_recall, 4),
        "n_planted": n_planted,
        "n_planted_caught": n_planted_caught,
        "n_real": n_real,
        "real_accept_kept": round(real_accept_kept, 4),
        "agreement": round(agreement, 4),
        "bar_pass": planted_recall >= 0.9,
        "n_total": len(rows),
    }


def esc(s):
    return html.escape(str(s if s is not None else ""))


def render_html(rows, summary, model, path):
    trs = []
    for r in rows:
        cls = "ok" if r["correct"] else "bad"
        planted_label = "planted" if r["is_planted"] else "real"
        trs.append(f"""<tr class="{cls}">
<td>{esc(r['candidate_id'])}<br><small>{esc(r.get('planted_error_type') or '')}</small></td>
<td>{planted_label}</td>
<td>{esc(r['expected'])}</td>
<td>{esc(r['verdict'])}</td>
<td>{esc(r.get('confidence', ''))}</td>
<td>{esc(r.get('reason', ''))}</td>
</tr>""")

    bar_color = "#2da44e" if summary["bar_pass"] else "#cf222e"
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>③-C judge 校准</title>
<style>
body{{font:14px/1.55 -apple-system,"PingFang SC",sans-serif;margin:0;background:#f6f8fb;color:#1c2530}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 18px 60px}}
h1{{font-size:22px;margin:0 0 12px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 18px}}
.stat{{background:#fff;border:1px solid #e1e6ee;border-radius:8px;padding:10px 14px}}
.stat b{{font-size:22px}}
.bar{{background:{bar_color};color:#fff;border-radius:6px;padding:4px 10px;margin:0 0 18px;display:inline-block}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e1e6ee;border-radius:8px;overflow:hidden}}
th,td{{padding:8px 10px;border-bottom:1px solid #eef1f4;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#edf2f7;color:#526071}}
tr.ok td{{background:#f2fbf5}} tr.bad td{{background:#fff1f1}}
small{{color:#697589}}
</style></head><body><div class="wrap">
<h1>③-C judge 校准 — {esc(model)}</h1>
<div class="bar">达标线 planted_recall ≥ 0.9 → {'✓ PASS' if summary['bar_pass'] else '✗ FAIL'}</div>
<div class="stats">
<div class="stat">planted_recall<br><b>{summary['planted_recall']:.3f}</b></div>
<div class="stat">real_accept_kept<br><b>{summary['real_accept_kept']:.3f}</b></div>
<div class="stat">agreement<br><b>{summary['agreement']:.3f}</b></div>
<div class="stat">planted<br><b>{summary['n_planted']}</b></div>
<div class="stat">planted_caught<br><b>{summary['n_planted_caught']}</b></div>
<div class="stat">real<br><b>{summary['n_real']}</b></div>
</div>
<table>
<tr><th>candidate_id</th><th>类型</th><th>期望</th><th>judge</th><th>置信</th><th>理由</th></tr>
{''.join(trs)}
</table></div></body></html>"""
    Path(path).write_text(doc, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--judge-provider", default="openai", choices=["anthropic", "openai"])
    ap.add_argument("--judge-model", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = make_client(
        args.judge_provider, args.judge_model,
        str(out_dir / "judge_calibration_calls.jsonl"),
    )
    results_path = out_dir / "judge_calibration.jsonl"
    existing = read_existing(results_path)

    rows = []
    for rec in read_golden(args.golden):
        cid = f'{rec["from"]}|{rec["to"]}|{rec["rel"]}'
        if cid in existing:
            rows.append(existing[cid])
            print(f"{len(rows):02d} {cid}: reused {existing[cid]['verdict']}", flush=True)
            continue

        cand = row_to_candidate(rec)
        for attempt in range(2):
            try:
                judgment = judge_candidate(client, cand)
                break
            except Exception:
                if attempt == 1:
                    raise
                time.sleep(2)

        # planted: judge must NOT accept (reject or manual_review = caught)
        # real: gold_decision is the human truth
        is_planted = bool(rec.get("is_planted"))
        expected = "not-accept" if is_planted else rec.get("gold_decision", "")
        verdict = judgment.decision
        correct = (verdict != "accept") if is_planted else (verdict == rec.get("gold_decision"))

        row = {
            "candidate_id": cid,
            "from": rec["from"],
            "to": rec["to"],
            "rel": rec["rel"],
            "stratum": rec.get("stratum"),
            "is_planted": is_planted,
            "planted_error_type": rec.get("planted_error_type"),
            "gold_decision": rec.get("gold_decision"),
            "expected": expected,
            "verdict": verdict,
            "confidence": judgment.confidence,
            "reason": judgment.reason,
            "correct": correct,
        }
        rows.append(row)
        with open(results_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"{len(rows):02d} {cid}: expected={expected} got={verdict} conf={judgment.confidence:.2f}",
            flush=True,
        )

    summary = score_calibration(rows)
    summary["model"] = args.judge_model

    # rewrite JSONL with all rows + _summary
    with open(results_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps({"_summary": summary}, ensure_ascii=False) + "\n")

    html_path = out_dir / "judge_calibration.html"
    render_html(rows, summary, args.judge_model, html_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report: {html_path}")


if __name__ == "__main__":
    main()
