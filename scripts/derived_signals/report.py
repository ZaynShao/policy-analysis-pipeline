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


def _sample_rows(rows: list[dict], title_key: str, id_key: str, limit: int = 40) -> str:
    body = []
    for row in rows[:limit]:
        themes = "、".join(row.get("theme_ids") or []) or "未命中"
        body.append(
            "<tr>"
            f"<td>{_esc(row.get(id_key, ''))}</td>"
            f"<td>{_esc(row.get(title_key, ''))}</td>"
            f"<td>{_esc(themes)}</td>"
            f"<td>{_esc(row.get('evidence', ''))}</td>"
            "</tr>"
        )
    if not body:
        return '<tr><td colspan="4">无</td></tr>'
    return "".join(body)


def _blocked_rows(rows: list[dict], limit: int = 40) -> str:
    body = []
    for row in rows[:limit]:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('source_kind', ''))}</td>"
            f"<td>{_esc(row.get('block_key', ''))}</td>"
            f"<td>{_esc(row.get('title', ''))}</td>"
            f"<td>{_esc('、'.join(row.get('queue_reasons') or []))}</td>"
            "</tr>"
        )
    if not body:
        return '<tr><td colspan="4">无</td></tr>'
    return "".join(body)


def _shell(title: str, subtitle: str, cards: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
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
<h1>{_esc(title)}</h1>
<div class="sub">{subtitle}</div>
<section class="grid">{cards}</section>
{body}
</main>
</body>
</html>
"""


def render_preview_html(
    summary: dict,
    commentary_rows: list[dict],
    market_rows: list[dict],
    blocked_rows: list[dict],
    out_path: Path,
) -> Path:
    cards = _cards(
        [
            ("评论信号", summary["commentary_signals"]),
            ("市场信号", summary["market_intel_signals"]),
            ("拦截信号", summary["blocked_signals"]),
            ("评论人工池", summary["commentary_review_queue"]),
            ("市场人工池", summary["market_intel_review_queue"]),
        ]
    )
    targets = "".join(f"<li><code>{_esc(path)}</code></li>" for path in summary["will_write"])
    body = f"""
<h2>结论</h2>
<div class="note">
  <p>这是派生信号 preview:只读上游 dry-run 的已产出 signal,不写资料库、不改 raw、不调用模型。</p>
  <p>人工池是发布闸门:凡与 review queue 重叠的 signal,本 preview 会拦截并写入 <code>blocked_signals.jsonl</code>,不会进入待发布派生文件。这就是不消费人工池的含义。后续人工裁决必须回到正常 dry-run/apply 流程。</p>
  <p>评论信号是内部校准参数,市场信号是内部验证参数。消费层默认不把它们作为外显方法论,仅在追溯、审计或分析师复核时展开。</p>
</div>

<h2>计划写入路径</h2>
<ul>{targets}</ul>

<h2>评论信号样例</h2>
<table><tr><th>ID</th><th>标题</th><th>主题</th><th>证据</th></tr>{_sample_rows(commentary_rows, "title", "commentary_id")}</table>

<h2>市场信号样例</h2>
<table><tr><th>ID</th><th>标题</th><th>主题</th><th>证据</th></tr>{_sample_rows(market_rows, "title", "market_signal_id")}</table>

<h2>人工池拦截样例</h2>
<table><tr><th>来源</th><th>拦截键</th><th>标题</th><th>原因</th></tr>{_blocked_rows(blocked_rows)}</table>
"""
    doc = _shell("派生信号 preview", "把评论与市场信号整理为 vault 派生层的预览输出。", cards, body)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def render_apply_html(summary: dict, out_path: Path) -> Path:
    cards = _cards(
        [
            ("写入文件", len(summary["written"])),
            ("评论信号", summary["commentary_signals"]),
            ("市场信号", summary["market_intel_signals"]),
            ("raw 写入", 0),
        ]
    )
    rows = "".join(
        f"<tr><td><code>{_esc(path)}</code></td><td>整体重写</td></tr>"
        for path in summary["written"]
    )
    body = f"""
<h2>结论</h2>
<div class="note">
  <p>本 apply 只从 preview 输出写入 <code>1_extracted/</code> 下的两个派生文件。</p>
  <p>它不读取上游人工池,不写 <code>0_raw/</code>,不修改政策或评论原始材料。</p>
</div>

<h2>写入清单</h2>
<table><tr><th>路径</th><th>方式</th></tr>{rows}</table>
"""
    doc = _shell("派生信号 apply", "把已批准 preview 写入 vault 派生层。", cards, body)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
