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


def _sample_policy_rows(rows: list[dict], limit: int = 40) -> str:
    body = []
    for row in rows[:limit]:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('policy_id', ''))}</td>"
            f"<td>{_esc(row.get('commentary_signal_count', 0))}</td>"
            f"<td>{_esc(row.get('market_signal_count', 0))}</td>"
            f"<td>{_esc(row.get('attention_level', ''))}</td>"
            f"<td>{_esc(row.get('validation_level', ''))}</td>"
            f"<td>{_esc(row.get('certainty_adjustment', ''))}</td>"
            f"<td>{_esc('、'.join(row.get('internal_notes') or []))}</td>"
            "</tr>"
        )
    return "".join(body) or '<tr><td colspan="7">无</td></tr>'


def _sample_theme_rows(rows: list[dict], limit: int = 40) -> str:
    body = []
    for row in rows[:limit]:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('theme_id', ''))}</td>"
            f"<td>{_esc(row.get('commentary_signal_count', 0))}</td>"
            f"<td>{_esc(row.get('market_signal_count', 0))}</td>"
            f"<td>{_esc(row.get('heat_level', ''))}</td>"
            f"<td>{_esc(row.get('validation_level', ''))}</td>"
            f"<td>{_esc(row.get('coverage_warning', ''))}</td>"
            "</tr>"
        )
    return "".join(body) or '<tr><td colspan="6">无</td></tr>'


def _sample_region_rows(rows: list[dict], limit: int = 40) -> str:
    body = []
    for row in rows[:limit]:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('region_name', ''))}</td>"
            f"<td>{_esc(row.get('region_code', ''))}</td>"
            f"<td>{_esc(row.get('market_signal_count', 0))}</td>"
            f"<td>{_esc('、'.join(row.get('theme_ids') or []))}</td>"
            f"<td>{_esc(row.get('validation_level', ''))}</td>"
            "</tr>"
        )
    return "".join(body) or '<tr><td colspan="5">无</td></tr>'


def render_preview_html(
    summary: dict,
    policy_rows: list[dict],
    theme_rows: list[dict],
    region_rows: list[dict],
    out_path: Path,
) -> Path:
    cards = _cards(
        [
            ("评论信号", summary["accepted_commentary_signals"]),
            ("市场信号", summary["accepted_market_signals"]),
            ("blocked 审计", summary["blocked_signal_count"]),
            ("policy context", summary["policy_context_count"]),
            ("theme context", summary["theme_context_count"]),
            ("region context", summary["region_context_count"]),
        ]
    )
    warning_rows = _counter_rows(summary.get("coverage_warnings", {}))
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>③-D signal_context preview</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f8fb;color:#172033;line-height:1.6}}
main{{max-width:1240px;margin:0 auto;padding:34px 24px 64px}}
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
<h1>③-D signal_context preview</h1>
<div class="sub">把已发布评论信号和市场信号整理为内部 policy/theme/region context。</div>
<section class="grid">{cards}</section>

<h2>结论</h2>
<div class="note">
  <p>本 preview 只读 vault 已发布的 accepted signals,不写资料库、不写 raw、不 apply、不调用模型。</p>
  <p>blocked signals 只作为审计门使用,不读取 blocked signals 当 accepted,也不进入任何 context。</p>
  <p>这些 context 是内部校准参数,用于后续调整注意力、确定性和验证强弱;默认消费层不展示原始评论标题、市场标题或证据片段。</p>
</div>

<h2>覆盖警示</h2>
<table><tr><th>warning</th><th>数量</th></tr>{warning_rows}</table>

<h2>policy context 样例</h2>
<table><tr><th>policy</th><th>评论</th><th>市场</th><th>attention</th><th>validation</th><th>certainty</th><th>notes</th></tr>{_sample_policy_rows(policy_rows)}</table>

<h2>theme context 样例</h2>
<table><tr><th>theme</th><th>评论</th><th>市场</th><th>heat</th><th>validation</th><th>warning</th></tr>{_sample_theme_rows(theme_rows)}</table>

<h2>region context 样例</h2>
<table><tr><th>region</th><th>code</th><th>市场</th><th>themes</th><th>validation</th></tr>{_sample_region_rows(region_rows)}</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
