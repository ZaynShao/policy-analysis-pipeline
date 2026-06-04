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
    ranked = sorted(
        rows,
        key=lambda row: (
            -len(row.get("audit_refs", {}).get("relation_candidate_ids", [])),
            -row.get("signal_summary", {}).get("commentary_signal_count", 0),
            -row.get("signal_summary", {}).get("market_signal_count", 0),
            row.get("policy_id", ""),
        ),
    )
    for row in ranked[:limit]:
        rel = row.get("relation_summary", {})
        sig = row.get("signal_summary", {})
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('policy_id', ''))}</td>"
            f"<td>{_esc(rel.get('references_out', 0) + rel.get('references_in', 0))}</td>"
            f"<td>{_esc(rel.get('cites_basis_out', 0) + rel.get('cites_basis_in', 0))}</td>"
            f"<td>{_esc(rel.get('supersedes_out', 0))}/{_esc(rel.get('superseded_by_count', 0))}</td>"
            f"<td>{_esc(rel.get('clarifies_out', 0))}/{_esc(rel.get('clarified_by_count', 0))}</td>"
            f"<td>{_esc(sig.get('commentary_signal_count', 0))}</td>"
            f"<td>{_esc(sig.get('market_signal_count', 0))}</td>"
            f"<td>{_esc(sig.get('commentary_attention', ''))}</td>"
            f"<td>{_esc(sig.get('market_validation', ''))}</td>"
            f"<td>{_esc(sig.get('certainty_adjustment', ''))}</td>"
            f"<td>{_esc('、'.join(row.get('analysis_flags') or []))}</td>"
            "</tr>"
        )
    return "".join(body) or '<tr><td colspan="11">无</td></tr>'


def render_preview_html(summary: dict, rows: list[dict], out_path: Path) -> Path:
    cards = _cards(
        [
            ("关系候选", summary["relation_candidate_count"]),
            ("signal policy", summary["policy_context_count"]),
            ("analysis rows", summary["analysis_context_count"]),
            ("关系覆盖", summary["rows_with_relation_context"]),
            ("信号覆盖", summary["rows_with_signal_context"]),
            ("两者都有", summary["rows_with_both"]),
        ]
    )
    flag_rows = _counter_rows(summary.get("rows_by_flag", {}))
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>③-E analysis_context preview</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f8fb;color:#172033;line-height:1.6}}
main{{max-width:1320px;margin:0 auto;padding:34px 24px 64px}}
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
@media (max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<main>
<h1>③-E analysis_context preview</h1>
<div class="sub">把③-B高精度政策关系候选和③-D已闭环 signal_context 合并为④可读取的统一上下文。</div>
<section class="grid">{cards}</section>

<h2>边界</h2>
<div class="note">
  <p>本 preview 只写工程仓 <code>state/</code>,不写资料库、不写 raw、不 apply、不调用模型。</p>
  <p>它不是最终业务洞察,也不是对外报告或卡片;④ 默认读取 analysis_context,而不是直接读取 raw relations 或 raw signals。</p>
  <p>外部观点和市场信号只作为内部注意力、验证强弱和确定性调整参数;默认消费层不展开原始评论或市场证据。</p>
</div>

<h2>flags 分布</h2>
<table><tr><th>flag</th><th>政策数</th></tr>{flag_rows}</table>

<h2>policy analysis_context 样例</h2>
<table>
<tr><th>policy</th><th>references</th><th>basis</th><th>supersedes/by</th><th>clarifies/by</th><th>评论</th><th>市场</th><th>attention</th><th>validation</th><th>certainty</th><th>flags</th></tr>
{_sample_rows(rows)}
</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
