from __future__ import annotations

import html
from pathlib import Path


def _esc(value) -> str:
    return html.escape(str(value))


def _cards(items: list[tuple[str, object]]) -> str:
    return "".join(
        f'<div class="card"><div class="label">{_esc(label)}</div><div class="num">{_esc(value)}</div></div>'
        for label, value in items
    )


def _counter_rows(counter: dict[str, int], empty: str = "无") -> str:
    rows = [
        f"<tr><td>{_esc(key)}</td><td>{_esc(value)}</td></tr>"
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    return "".join(rows) or f'<tr><td colspan="2">{_esc(empty)}</td></tr>'


def _candidate_rows(rows: list[dict], limit: int = 80) -> str:
    body = []
    for row in rows[:limit]:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('rel', ''))}</td>"
            f"<td>{_esc(row.get('from', ''))}</td>"
            f"<td>{_esc(row.get('to', ''))}</td>"
            f"<td>{_esc(row.get('doc_number', ''))}</td>"
            f"<td>{_esc(row.get('evidence', ''))}</td>"
            f"<td>{_esc(', '.join(row.get('rules') or []))}</td>"
            "</tr>"
        )
    if not body:
        return '<tr><td colspan="6">无</td></tr>'
    return "".join(body)


def render_preview_html(summary: dict, candidates: list[dict], out_path: Path) -> Path:
    cards = _cards(
        [
            ("tracked raw", summary["tracked_policy_count"]),
            ("未跟踪 raw", summary["untracked_policy_count"]),
            ("候选关系", summary["candidate_count"]),
            ("文号目标", summary["official_number_targets"]),
        ]
    )
    relation_rows = _counter_rows(summary.get("rows_by_relation", {}))
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>③-B 高精度政策关系 preview</title>
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
<h1>③-B 高精度政策关系 preview</h1>
<div class="sub">从当前 tracked raw 政策正文重新抽取高精度候选关系。</div>
<section class="grid">{cards}</section>

<h2>结论</h2>
<div class="note">
  <p>本 preview 只读当前 git tracked raw,不写资料库、不写 raw、不 apply、不调用模型。</p>
  <p>旧 <code>1_extracted/relations</code> 不作为 accepted 输入;本报告产出的是当前语料上的候选关系,后续 apply 需要单独批准。</p>
  <p>规则范围只覆盖 <code>references</code>、<code>cites_basis</code>、<code>supersedes</code>、<code>clarifies</code>。语义关系仍等 ②-B 覆盖稳定后处理。</p>
</div>

<h2>关系类型</h2>
<table><tr><th>rel</th><th>候选数</th></tr>{relation_rows}</table>

<h2>候选样例</h2>
<table><tr><th>rel</th><th>from</th><th>to</th><th>文号</th><th>证据</th><th>规则</th></tr>{_candidate_rows(candidates)}</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
