from __future__ import annotations

from collections import Counter
import html
from pathlib import Path

from .extractor import MarketSignal


SIGNAL_TYPE_ZH = {
    "project_list": "项目清单",
    "competitive_allocation": "竞配/评分",
    "project_commissioned": "并网/建成",
    "pilot_landing": "试点落地",
    "capacity_disclosure": "容量披露",
    "subsidy_list": "补贴清单",
    "price_signal": "价格信号",
    "trading_result": "交易结果",
    "tender_procurement": "招标采购",
    "market_access": "准入许可",
    "project_progress": "项目推进",
    "project_case": "典型案例",
    "unknown": "未知",
}

BUSINESS_LINE_ZH = {
    "charging": "充电",
    "power": "电力",
    "fuel": "加油",
}


def _esc(value) -> str:
    return html.escape(str(value))


def _rows(signals: list[MarketSignal], theme_labels: dict[str, str], limit: int = 60) -> str:
    rows = []
    for signal in signals[:limit]:
        themes = "、".join(theme_labels.get(t, t) for t in signal.theme_ids) or "未命中"
        lines = "、".join(BUSINESS_LINE_ZH.get(line, line) for line in signal.business_lines) or "未判定"
        rows.append(
            "<tr>"
            f"<td>{_esc(signal.title)}</td>"
            f"<td>{_esc(signal.source_pid)}</td>"
            f"<td>{_esc(signal.region.get('name') or '未知')}</td>"
            f"<td>{_esc(themes)}</td>"
            f"<td>{_esc(lines)}</td>"
            f"<td>{_esc(SIGNAL_TYPE_ZH.get(signal.signal_type, signal.signal_type))}</td>"
            f"<td>{_esc(signal.observed_date)}</td>"
            f"<td>{_esc(signal.evidence)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="8">无</td></tr>'
    return "".join(rows)


def _queue_rows(queue: list[dict], limit: int = 60) -> str:
    rows = []
    for row in queue[:limit]:
        rows.append(
            "<tr>"
            f"<td>{_esc(row.get('source_pid', ''))}</td>"
            f"<td>{_esc(row.get('title', ''))}</td>"
            f"<td>{_esc(row.get('reason', ''))}</td>"
            f"<td>{_esc(row.get('evidence', ''))}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="4">无</td></tr>'
    return "".join(rows)


def render_html(
    signals: list[MarketSignal],
    review_queue: list[dict],
    summary: dict,
    theme_labels: dict[str, str],
    out_path: Path,
) -> Path:
    cards = "".join(
        f'<div class="card"><div class="label">{_esc(label)}</div><div class="num">{_esc(value)}</div></div>'
        for label, value in [
            ("manifest 行", summary["manifest_rows"]),
            ("输出 signal", summary["emitted_signals"]),
            ("人工池", summary["review_queue"]),
            ("可定位 raw", summary["located_raw"]),
        ]
    )
    type_rows = "".join(
        f"<tr><td>{_esc(SIGNAL_TYPE_ZH.get(key, key))}</td><td>{count}</td></tr>"
        for key, count in summary["by_signal_type"].items()
    )
    theme_rows = "".join(
        f"<tr><td>{_esc(theme_labels.get(key, key))}</td><td>{count}</td></tr>"
        for key, count in summary["by_theme"].items()
    )
    queue_reason_rows = "".join(
        f"<tr><td>{_esc(key)}</td><td>{count}</td></tr>"
        for key, count in summary["by_queue_reason"].items()
    )
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>市场情报信号 dry-run</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f8fb;color:#172033;line-height:1.6}}
main{{max-width:1180px;margin:0 auto;padding:34px 24px 64px}}
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
<h1>市场情报信号 dry-run</h1>
<div class="sub">本报告只读扫描 <code>market_intel_manifest.jsonl</code> 和当前 <code>0_raw/policies</code>,把已登记的第三源材料转成内部验证信号。不写资料库、不改 raw、不调用模型。</div>
<section class="grid">{cards}</section>

<h2>结论</h2>
<div class="note">
  <p>市场情报在这里的角色是内部验证:提示哪里已有项目、容量、补贴、价格、许可、交易或落地动作。它不直接覆盖政策事实、主题归属或 business_view 分数,也不作为对外消费层的显性市场来源。</p>
  <p>第一版只升级既有 manifest,不新增采集源。无法定位、主题未命中、地区未知、日期缺失或类型未知的行进入人工池,后续裁决仍要回正常 dry-run/apply 流程。</p>
</div>

<h2>信号类型分布</h2>
<table><tr><th>类型</th><th>数量</th></tr>{type_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>主题命中分布</h2>
<table><tr><th>主题</th><th>数量</th></tr>{theme_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>人工池原因</h2>
<table><tr><th>原因</th><th>数量</th></tr>{queue_reason_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>信号样例</h2>
<table><tr><th>标题</th><th>源 PID</th><th>地区</th><th>主题</th><th>业务线</th><th>类型</th><th>日期</th><th>证据片段</th></tr>{_rows(signals, theme_labels)}</table>

<h2>人工池样例</h2>
<table><tr><th>源 PID</th><th>标题</th><th>原因</th><th>证据片段</th></tr>{_queue_rows(review_queue)}</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
