import argparse
import html
import json
from pathlib import Path
from typing import Optional, Union

from .manual_review_server import load_decisions, load_review_items, split_review_items


PathLike = Union[str, Path]


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _accepted_drafts(state: Path) -> list:
    return _read_jsonl(state / "proposed_changes" / "drafts_full.jsonl")


def build_post_review_summary(state: PathLike) -> dict:
    state = Path(state)
    accepted = _accepted_drafts(state)
    all_items = load_review_items(state)
    manual_items, technical_items = split_review_items(all_items)
    queue_by_hash = {item["queue_record_sha256"]: item for item in all_items}
    manual_hashes = {item["queue_record_sha256"] for item in manual_items}

    validated = []
    invalid = []
    for decision in load_decisions(state):
        item = queue_by_hash.get(decision.get("queue_record_sha256"))
        if item and item["pid"] == decision.get("pid") and decision.get("queue_record_sha256") in manual_hashes:
            row = dict(decision)
            row["queue_stage"] = item["queue_stage"]
            row["queue_reason"] = item["queue_reason"]
            validated.append(row)
        else:
            invalid.append(decision)

    decided_hashes = {row["queue_record_sha256"] for row in validated}
    remaining_manual = [item for item in manual_items if item["queue_record_sha256"] not in decided_hashes]

    return {
        "state_dir": str(state.resolve()),
        "accepted_draft_count": len(accepted),
        "accepted_drafts": accepted,
        "validated_manual_decision_count": len(validated),
        "validated_manual_decisions": validated,
        "invalid_manual_decision_count": len(invalid),
        "invalid_manual_decisions": invalid,
        "technical_rerun_count": len(technical_items),
        "technical_rerun_items": technical_items,
        "remaining_manual_count": len(remaining_manual),
        "remaining_manual_items": remaining_manual,
        "manual_decisions_direct_apply": False,
    }


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _theme_text(row: dict) -> str:
    labels = row.get("target_theme_labels") or row.get("themes") or row.get("target_themes") or []
    ids = row.get("target_themes") or row.get("themes") or []
    if labels and ids and labels != ids:
        return ", ".join(f"{label} ({tid})" for label, tid in zip(labels, ids))
    return ", ".join(str(x) for x in labels or ids)


def render_post_review_preview(state: PathLike, out_path: Optional[PathLike] = None) -> str:
    state = Path(state)
    out = Path(out_path) if out_path else state / "reports" / "post_review_preview_zh.html"
    summary = build_post_review_summary(state)

    accepted_rows = "".join(
        f"<tr><td>{_esc(row.get('pid'))}</td><td>{_esc(', '.join(row.get('themes') or []))}</td>"
        f"<td>{_esc(row.get('primary_theme'))}</td><td>{_esc(row.get('重要性'))}</td></tr>"
        for row in summary["accepted_drafts"]
    ) or "<tr><td colspan=\"4\">无</td></tr>"

    manual_rows = "".join(
        f"<tr><td>{_esc(row.get('pid'))}</td><td>{_esc(row.get('decision'))}</td>"
        f"<td>{_esc(_theme_text(row))}</td><td>{_esc(row.get('primary_theme_label') or row.get('primary_theme'))}</td>"
        f"<td>{_esc(row.get('importance'))}</td><td>{_esc(row.get('note'))}</td>"
        f"<td><code>{_esc(row.get('queue_record_sha256'))}</code></td></tr>"
        for row in summary["validated_manual_decisions"]
    ) or "<tr><td colspan=\"7\">无</td></tr>"

    tech_rows = "".join(
        f"<tr><td>{_esc(item.get('pid'))}</td><td>{_esc(item.get('queue_stage'))}</td>"
        f"<td>{_esc(item.get('queue_reason'))}</td><td><code>{_esc(item.get('queue_record_sha256'))}</code></td></tr>"
        for item in summary["technical_rerun_items"]
    ) or "<tr><td colspan=\"4\">无</td></tr>"

    remaining_rows = "".join(
        f"<tr><td>{_esc(item.get('pid'))}</td><td>{_esc(item.get('queue_stage'))}</td>"
        f"<td>{_esc(item.get('queue_reason'))}</td></tr>"
        for item in summary["remaining_manual_items"]
    ) or "<tr><td colspan=\"3\">无</td></tr>"

    invalid_rows = "".join(
        f"<tr><td>{_esc(row.get('pid'))}</td><td><code>{_esc(row.get('queue_record_sha256'))}</code></td>"
        f"<td>{_esc(row.get('decision'))}</td></tr>"
        for row in summary["invalid_manual_decisions"]
    ) or "<tr><td colspan=\"3\">无</td></tr>"

    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>②-B post-review preview</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;margin:28px;background:#f8fafc;color:#172033;line-height:1.55}}
h1{{font-size:24px;margin-bottom:6px}} h2{{font-size:18px;margin-top:24px;border-left:4px solid #2563eb;padding-left:10px}}
.sub{{color:#64748b}} .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}
.card{{background:#fff;border:1px solid #d8dee8;border-radius:8px;padding:14px}} .num{{font-size:28px;font-weight:700;color:#0f766e}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}} th,td{{border:1px solid #d8dee8;padding:7px 8px;vertical-align:top;text-align:left}} th{{background:#eef2f7}}
code{{font-size:11px;color:#475569;word-break:break-all}} .warn{{background:#fff7ed;border:1px solid #fed7aa;padding:10px;border-radius:8px}}
</style></head><body>
<h1>②-B post-review preview</h1>
<p class="sub">state: <code>{_esc(summary['state_dir'])}</code></p>
<div class="warn">人工裁决已闭环,但不是完整 draft,不能直接 apply。它们是下一轮 bounded dry-run / regression 的数据层预期;通过正常流水线生成完整 draft 后再进入 apply preview。</div>
<div class="grid">
<div class="card"><div class="num">{summary['accepted_draft_count']}</div><div>原 dry-run accepted</div></div>
<div class="card"><div class="num">{summary['validated_manual_decision_count']}</div><div>人工裁决已闭环</div></div>
<div class="card"><div class="num">{summary['technical_rerun_count']}</div><div>技术复跑项</div></div>
<div class="card"><div class="num">{summary['remaining_manual_count']}</div><div>剩余人工待办</div></div>
</div>
<h2>可进入 apply preview 的原 dry-run accepted</h2>
<table><tr><th>PID</th><th>Themes</th><th>Primary</th><th>重要性</th></tr>{accepted_rows}</table>
<h2>人工裁决已闭环,但不是完整 draft</h2>
<table><tr><th>PID</th><th>裁决</th><th>Themes</th><th>Primary</th><th>重要性</th><th>备注</th><th>queue hash</th></tr>{manual_rows}</table>
<h2>技术复跑项</h2>
<table><tr><th>PID</th><th>阶段</th><th>原因</th><th>queue hash</th></tr>{tech_rows}</table>
<h2>剩余人工待办</h2>
<table><tr><th>PID</th><th>阶段</th><th>原因</th></tr>{remaining_rows}</table>
<h2>无效/未对回人工裁决</h2>
<table><tr><th>PID</th><th>queue hash</th><th>裁决</th></tr>{invalid_rows}</table>
</body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return str(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    print(render_post_review_preview(args.state, args.out))


if __name__ == "__main__":
    main()
