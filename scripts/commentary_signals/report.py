from __future__ import annotations

from collections import Counter
import html
from pathlib import Path

from .extractor import CommentarySignal


ROLE_ZH = {
    "risk": "风险",
    "opportunity": "机会",
    "execution": "执行",
    "attention": "关注",
    "interpretation": "解读",
    "noise": "噪声",
}


def _esc(value) -> str:
    return html.escape(str(value))


def _theme_name(theme_id: str, theme_labels: dict[str, str]) -> str:
    label = theme_labels.get(theme_id)
    return f"{label}({theme_id})" if label and label != theme_id else theme_id


def _signal_rows(signals: list[CommentarySignal], theme_labels: dict[str, str], limit: int = 50) -> str:
    rows = []
    for signal in signals[:limit]:
        themes = "、".join(_theme_name(t, theme_labels) for t in signal.theme_ids) or "未命中"
        rows.append(
            "<tr>"
            f"<td>{_esc(signal.title)}</td>"
            f"<td>{_esc('、'.join(signal.related_policy_ids))}</td>"
            f"<td>{_esc(themes)}</td>"
            f"<td>{_esc(ROLE_ZH.get(signal.signal_role, signal.signal_role))}</td>"
            f"<td>{_esc(signal.confidence)}</td>"
            f"<td>{_esc(signal.evidence)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6">无</td></tr>'
    return "".join(rows)


def _queue_rows(queue: list[dict], limit: int = 50) -> str:
    rows = []
    for row in queue[:limit]:
        rows.append(
            "<tr>"
            f"<td>{_esc(row.get('title', ''))}</td>"
            f"<td>{_esc('、'.join(row.get('related_policy_ids') or []))}</td>"
            f"<td>{_esc(row.get('reason', ''))}</td>"
            f"<td>{_esc(row.get('evidence', ''))}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="4">无</td></tr>'
    return "".join(rows)


def render_html(
    signals: list[CommentarySignal],
    review_queue: list[dict],
    summary: dict,
    theme_labels: dict[str, str],
    out_path: Path,
) -> Path:
    role_rows = "".join(
        f"<tr><td>{_esc(ROLE_ZH.get(role, role))}</td><td>{count}</td></tr>"
        for role, count in Counter(s.signal_role for s in signals).most_common()
    )
    theme_rows = "".join(
        f"<tr><td>{_esc(_theme_name(theme_id, theme_labels))}</td><td>{count}</td></tr>"
        for theme_id, count in Counter(t for s in signals for t in s.theme_ids).most_common()
    )
    cards = "".join(
        f'<div class="card"><div class="label">{_esc(label)}</div><div class="num">{_esc(value)}</div></div>'
        for label, value in [
            ("评论 raw", summary["total_commentaries"]),
            ("已有政策关联", summary["linked_commentaries"]),
            ("输出 signal", summary["emitted_signals"]),
            ("人工池", summary["review_queue"]),
        ]
    )
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>评论校准信号 dry-run</title>
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
<h1>评论校准信号 dry-run</h1>
<div class="sub">本报告只读扫描 <code>0_raw/commentaries</code>,把已有政策关联的评论转成内部校准信号。不写资料库、不改 raw、不调用模型。</div>
<section class="grid">{cards}</section>

<h2>结论</h2>
<div class="note">
  <p>评论在这里的角色是内部校准和审计追溯:提示政策解读中的风险、机会、执行阻力和关注热度。它不直接覆盖政策事实、主题归属或 business_view 分数,也不作为对外消费层的显性外部观点来源。</p>
  <p>第一版只处理已有 <code>related_policy</code> 的评论。已关联但未命中主题的评论进入人工池,由人工判断主题归属后再回正常 dry-run/apply 流程。</p>
</div>

<h2>信号角色分布</h2>
<table><tr><th>角色</th><th>数量</th></tr>{role_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>主题命中分布</h2>
<table><tr><th>主题</th><th>数量</th></tr>{theme_rows or '<tr><td colspan="2">无</td></tr>'}</table>

<h2>信号样例</h2>
<table><tr><th>评论标题</th><th>关联政策</th><th>主题</th><th>角色</th><th>置信度</th><th>证据片段</th></tr>{_signal_rows(signals, theme_labels)}</table>

<h2>人工池样例</h2>
<table><tr><th>评论标题</th><th>关联政策</th><th>原因</th><th>证据片段</th></tr>{_queue_rows(review_queue)}</table>
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
