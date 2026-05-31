from pathlib import Path
from collections import Counter

def render(drafts, queue, distribution_warns, golden_score, out_path: str) -> str:
    theme_count = Counter(t for d in drafts for t in (d.themes or []))
    imp_dist = Counter(d.importance for d in drafts)
    gated = sum(1 for d in drafts if d.gate_passed_deep)
    theme_rows = "".join(f"<tr><td>{t}</td><td>{c}</td></tr>"
                         for t, c in theme_count.most_common())
    imp_rows = "".join(f"<tr><td>重要性 {k}</td><td>{imp_dist[k]}</td></tr>"
                       for k in sorted(imp_dist, reverse=True))
    warn_html = "".join(f"<li>{w}</li>" for w in distribution_warns) or "<li>无</li>"
    q_html = "".join(f"<tr><td>{r.pid}</td><td>{r.stage}</td><td>{r.reason}</td></tr>"
                     for r in queue)
    gs = golden_score or {}
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>②-B dry-run 报告</title>
<style>body{{font-family:-apple-system,"PingFang SC";max-width:900px;margin:0 auto;padding:24px;background:#0f1115;color:#e6e9ef}}
table{{border-collapse:collapse;width:100%;margin:10px 0}}td,th{{border-bottom:1px solid #2a2f3a;padding:6px 10px;text-align:left}}
h2{{border-left:3px solid #6ab7ff;padding-left:10px}}</style></head><body>
<h1>②-B 归属挂载 · dry-run 报告</h1>
<p>政策总数 {len(drafts)} · 过深档门 {gated} · 入队 {len(queue)}</p>
<h2>judge 校准</h2><p>召回 {gs.get('recall','-')} · 精度 {gs.get('precision','-')}</p>
<h2>分布告警</h2><ul>{warn_html}</ul>
<h2>重要性分布</h2><table>{imp_rows}</table>
<h2>theme 命中分布</h2><table><tr><th>theme</th><th>篇数</th></tr>{theme_rows}</table>
<h2>入队(需复核)</h2><table><tr><th>pid</th><th>阶段</th><th>原因</th></tr>{q_html}</table>
</body></html>"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
