"""dry-run HTML 验收报告:写了什么 vs 入队什么。自包含 HTML。"""
from __future__ import annotations
from pathlib import Path


def _field_repr(name, rf):
    """region 显示其 name,其余显示 value。"""
    if name == "region" and isinstance(rf.value, dict):
        return f"region→{rf.value.get('name')}"
    return f"{name}→{rf.value}"


def render(to_apply, queue, ledger_agree_rate, out_path: str):
    rows = []
    for ri in to_apply:
        chg = "; ".join(_field_repr(k, v) for k, v in ri.fields.items())
        rows.append(f"<tr><td>{ri.pid}</td><td>{chg}</td></tr>")
    qrows = []
    for ri in queue:
        for c in ri.conflicts:
            qrows.append(f"<tr><td>{ri.pid}</td><td>{c.field}</td><td>{c.reason}</td></tr>")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>②-A dry-run 验收</title>
<style>body{{font-family:'PingFang SC',sans-serif;max-width:920px;margin:0 auto;padding:32px;line-height:1.6}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th,td{{border-bottom:1px solid #e4e8ec;padding:7px 9px;text-align:left;vertical-align:top}}
th{{background:#f3f6f9}} .k{{color:#2E7D32;font-weight:700}} .q{{color:#C62828;font-weight:700}}</style></head>
<body>
<h1>②-A 确定性身份固化 · dry-run 验收</h1>
<p>将写 raw:<span class="k">{len(to_apply)}</span> 篇 · 入待裁决队列:<span class="q">{len(queue)}</span> 篇 ·
ledger 一致率:<b>{ledger_agree_rate:.1%}</b></p>
<h2>将写 raw({len(to_apply)})</h2>
<table><tr><th>pid</th><th>改动</th></tr>{''.join(rows)}</table>
<h2>入队列({len(qrows)} 条冲突)</h2>
<table><tr><th>pid</th><th>字段</th><th>原因</th></tr>{''.join(qrows)}</table>
</body></html>"""
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
