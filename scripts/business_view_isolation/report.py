from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

from .inventory import BusinessViewDecision


def _esc(value) -> str:
    return html.escape(str(value))


def _rows(decisions: list[BusinessViewDecision], action: str, limit: int = 40) -> str:
    rows = []
    for decision in [d for d in decisions if d.action == action][:limit]:
        rows.append(
            "<tr>"
            f"<td>{_esc(decision.pid)}</td>"
            f"<td>{_esc(decision.path)}</td>"
            f"<td>{_esc(', '.join(decision.reasons))}</td>"
            f"<td>{_esc(decision.extracted_by or '')}</td>"
            f"<td>{_esc(', '.join(decision.impact_keys))}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="5">无</td></tr>'
    return "".join(rows)


def render_html(decisions: list[BusinessViewDecision], summary: dict, out_path: Path) -> Path:
    reason_rows = "".join(
        f"<tr><td>{_esc(reason)}</td><td>{count}</td></tr>"
        for reason, count in Counter(reason for d in decisions for reason in d.reasons).most_common(12)
    )
    model_rows = "".join(
        f"<tr><td>{_esc(model or '(missing)')}</td><td>{count}</td></tr>"
        for model, count in summary.get("by_extracted_model", {}).items()
    )
    action_cards = "".join(
        f'<div class="card"><div class="label">{_esc(action)}</div><div class="num">{count}</div></div>'
        for action, count in summary["by_action"].items()
    )
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>旧 business_view 消费隔离 dry-run</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f8fb;color:#172033;line-height:1.6}}
main{{max-width:1160px;margin:0 auto;padding:34px 24px 64px}}
h1{{font-size:29px;margin:0 0 8px}}
h2{{font-size:20px;margin:28px 0 12px}}
.sub{{color:#667085;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.card{{background:#fff;border:1px solid #e1e6ef;border-radius:8px;padding:16px}}
.label{{color:#667085;font-size:13px}}
.num{{font-size:30px;font-weight:760;margin-top:4px}}
.note{{background:#fff;border-left:4px solid #2563eb;border-radius:8px;padding:14px 16px;border-top:1px solid #e1e6ef;border-right:1px solid #e1e6ef;border-bottom:1px solid #e1e6ef}}
table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e1e6ef}}
th,td{{border:1px solid #e1e6ef;padding:8px 9px;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#f1f5f9}}
code{{background:#eef2f7;padding:1px 5px;border-radius:4px}}
@media (max-width:860px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<main>
<h1>旧 business_view 消费隔离 dry-run</h1>
<div class="sub">本报告只读扫描 <code>_meta/business_view</code>,产出隔离清单和统计,不写资料库、不移动文件、不调用模型。</div>
<section class="grid">{action_cards}</section>

<h2>结论</h2>
<div class="note">
  <p>本 dry-run 的作用是把旧 <code>business_view</code> 从消费路径隔离出来的候选集合固定为机器可读 manifest。后续 apply 必须消费本次 dry-run 输出,先做库外 backup,再从可消费路径隔离旧文件。</p>
  <p>这不是逐篇人工改业务结论,也不是 PID 白名单。分类依据是全局来源字段、当前三业务影响 schema、旧口径污染和 YAML 可解析性。</p>
</div>

<h2>Top Reasons</h2>
<table><tr><th>原因</th><th>数量</th></tr>{reason_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>模型分布</h2>
<table><tr><th>extracted_model</th><th>数量</th></tr>{model_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>隔离候选样例</h2>
<table><tr><th>PID</th><th>路径</th><th>原因</th><th>extracted_by</th><th>影响分析 keys</th></tr>{_rows(decisions, "isolate_legacy")}</table>

<h2>人工复核样例</h2>
<table><tr><th>PID</th><th>路径</th><th>原因</th><th>extracted_by</th><th>影响分析 keys</th></tr>{_rows(decisions, "manual_review")}</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
