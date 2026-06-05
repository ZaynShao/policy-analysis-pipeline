from __future__ import annotations

import html
from pathlib import Path


def _esc(value) -> str:
    return html.escape(str(value))


def _cards(items: list) -> str:
    return "".join(
        f'<div class="card"><div class="label">{_esc(label)}</div><div class="num">{_esc(value)}</div></div>'
        for label, value in items
    )


def _counter_rows(counter: dict, empty: str = "无") -> str:
    rows = [
        f"<tr><td>{_esc(key)}</td><td>{_esc(value)}</td></tr>"
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    return "".join(rows) or f'<tr><td colspan="2">{_esc(empty)}</td></tr>'


def _relation_rows(rows: list[dict], show_confidence: bool, limit: int = 200) -> str:
    body = []
    for row in rows[:limit]:
        conf_cell = (
            f"<td>{_esc(row.get('confidence', ''))}</td>" if show_confidence else ""
        )
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('from', ''))}</td>"
            f"<td>{_esc(row.get('to', ''))}</td>"
            f"<td>{_esc(row.get('rel', ''))}</td>"
            + conf_cell +
            f"<td>{_esc(row.get('judge_reason', row.get('reason', '')))}</td>"
            "</tr>"
        )
    colspan = "5" if show_confidence else "4"
    if not body:
        return f'<tr><td colspan="{colspan}">无</td></tr>'
    return "".join(body)


def render_preview_html(summary: dict, accepted: list[dict], manual: list[dict], path: Path) -> Path:
    cards = _cards([
        ("候选关系", summary.get("candidate_count", 0)),
        ("门失败", summary.get("gate_failed", 0)),
        ("accepted", summary.get("accepted_count", 0)),
        ("待人工", summary.get("manual_count", 0)),
    ])
    by_rel_rows = _counter_rows(summary.get("accepted_by_relation", {}))
    accepted_header = "<tr><th>from</th><th>to</th><th>rel</th><th>confidence</th><th>judge_reason</th></tr>"
    accepted_body = _relation_rows(accepted, show_confidence=True)
    manual_header = "<tr><th>from</th><th>to</th><th>rel</th><th>judge_reason</th></tr>"
    manual_body = _relation_rows(manual, show_confidence=False)
    model = _esc(summary.get("model", "unknown"))

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>③-C 语义关系 preview</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f8fb;color:#172033;line-height:1.6}}
main{{max-width:1240px;margin:0 auto;padding:34px 24px 64px}}
h1{{font-size:29px;margin:0 0 8px}}
h2{{font-size:20px;margin:28px 0 12px}}
.sub{{color:#667085;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.card{{background:#fff;border:1px solid #e1e6ef;border-radius:8px;padding:16px}}
.label{{color:#667085;font-size:13px}}
.num{{font-size:30px;font-weight:760;margin-top:4px}}
.note{{background:#fff;border-left:4px solid #2563eb;border-radius:8px;padding:14px 16px;border-top:1px solid #e1e6ef;border-right:1px solid #e1e6ef;border-bottom:1px solid #e1e6ef}}
table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e1e6ef}}
th,td{{border:1px solid #e1e6ef;padding:8px 9px;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#f1f5f9}}
code{{background:#eef2f7;padding:1px 5px;border-radius:4px}}
@media (max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<main>
<h1>③-C 语义关系 preview</h1>
<div class="sub">候选关系经程序门 + LLM 受限判定后分层输出。<strong>preview only — 未 apply，不写 vault/raw。</strong></div>
<section class="grid">{cards}</section>

<h2>结论</h2>
<div class="note">
  <p><strong>本 preview 仅供审阅，不 apply、不写 vault、不写 raw。</strong>旧 <code>1_extracted/relations</code> 不作为 accepted 输入。</p>
  <p>模型：<code>{model}</code> &nbsp;|&nbsp; recommendation：<code>{_esc(summary.get("recommendation", ""))}</code></p>
  <p>后续 apply 需要单独批准。</p>
</div>

<h2>accepted 关系类型分布</h2>
<table><tr><th>rel</th><th>数量</th></tr>{by_rel_rows}</table>

<h2>accepted 关系（{_esc(summary.get("accepted_count", 0))} 条）</h2>
<table>{accepted_header}{accepted_body}</table>

<h2>待人工复核（{_esc(summary.get("manual_count", 0))} 条）</h2>
<table>{manual_header}{manual_body}</table>
</main>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path
