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


def _sample_rows(rows: list[dict], limit: int = 60) -> str:
    body = []
    risky = [row for row in rows if row.get("flags")]
    for row in (risky or rows)[:limit]:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('relation_file', ''))}</td>"
            f"<td>{_esc(row.get('rel', ''))}</td>"
            f"<td>{_esc(row.get('from', ''))}<br><span>{_esc(row.get('from_status', ''))}</span></td>"
            f"<td>{_esc(row.get('to', ''))}<br><span>{_esc(row.get('to_status', ''))}</span></td>"
            f"<td>{_esc('、'.join(row.get('flags') or []))}</td>"
            f"<td>{_esc(row.get('evidence', ''))}</td>"
            "</tr>"
        )
    if not body:
        return '<tr><td colspan="6">无</td></tr>'
    return "".join(body)


def render_preview_html(summary: dict, rows: list[dict], out_path: Path) -> Path:
    cards = _cards(
        [
            ("tracked raw", summary["tracked_policy_count"]),
            ("未跟踪 raw", summary["untracked_policy_count"]),
            ("关系行", summary["relation_rows"]),
            ("缺失端点行", summary["endpoint_missing_count"]),
            ("archive 行", summary["archive_relation_rows"]),
        ]
    )
    relation_files = _counter_rows(summary.get("relation_files", {}))
    relation_rows = _counter_rows(summary.get("rows_by_relation", {}))
    flag_rows = _counter_rows(summary.get("rows_by_flag", {}))
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>③-A 关系资产审计 preview</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f8fb;color:#172033;line-height:1.6}}
main{{max-width:1240px;margin:0 auto;padding:34px 24px 64px}}
h1{{font-size:29px;margin:0 0 8px}}
h2{{font-size:20px;margin:28px 0 12px}}
.sub{{color:#667085;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}}
.card{{background:#fff;border:1px solid #e1e6ef;border-radius:8px;padding:16px}}
.label{{color:#667085;font-size:13px}}
.num{{font-size:30px;font-weight:760;margin-top:4px}}
.note{{background:#fff;border-left:4px solid #2563eb;border-radius:8px;padding:14px 16px;border-top:1px solid #e1e6ef;border-right:1px solid #e1e6ef;border-bottom:1px solid #e1e6ef}}
table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e1e6ef}}
th,td{{border:1px solid #e1e6ef;padding:8px 9px;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#f1f5f9}}
code{{background:#eef2f7;padding:1px 5px;border-radius:4px}}
span{{color:#667085;font-size:12px}}
@media (max-width:960px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<main>
<h1>③-A 关系资产审计 preview</h1>
<div class="sub">只读盘点旧 <code>1_extracted/relations/*.jsonl</code> 与当前 tracked raw 政策语料的匹配状态。</div>
<section class="grid">{cards}</section>

<h2>结论</h2>
<div class="note">
  <p>本 preview 只读审计旧关系资产,不写资料库、不写 raw、不 apply、不调用模型。旧关系行只作为审计输入保留在 <code>source_row</code>,不能被视为新 ③ 的可消费关系输出。</p>
  <p>raw 基线只取 git 已跟踪的 <code>0_raw/policies/*.md</code>。未跟踪 raw 已排除,并单独计数,避免把本地临时材料悄悄纳入 ③ 审计基线。</p>
  <p>关系重生必须等 ② 归属稳定后,再按全局规则重建;当前输出用于判断旧资产哪里 stale、哪里缺端点、哪些关系类型需要高精度或低置信处理。</p>
</div>

<h2>关系文件</h2>
<table><tr><th>文件</th><th>行数</th></tr>{relation_files}</table>

<h2>关系类型</h2>
<table><tr><th>rel</th><th>行数</th></tr>{relation_rows}</table>

<h2>风险标记</h2>
<table><tr><th>flag</th><th>行数</th></tr>{flag_rows}</table>

<h2>样例行</h2>
<table><tr><th>文件</th><th>rel</th><th>from</th><th>to</th><th>flags</th><th>evidence</th></tr>{_sample_rows(rows)}</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
