"""SW11 CHECKPOINT:把新发现的商务/市监渠道(验证+候选)triage 成 HTML 给用户审。
候选分类:promotable(gov域+列表页样URL+商务/市监样host) vs junk(附件/单篇/oss)。
"""
from __future__ import annotations
import re
from pathlib import Path
from collections import Counter

from scripts.l1_collect.channel_catalog import load_catalog

CAT = Path("state/T1_channels/channel_catalog.yaml")
OUT = Path("state/l1_gate/discover_checkpoint_2026-06-08.html")

JUNK_HOST = ("oss-", "jcms", "attach")
JUNK_URL = (".pdf", ".doc", ".docx", ".xls")
# 单篇文章样式 /YYYYMM/t...html(非列表)
_ARTICLE = re.compile(r"/t\d{8}_\d+\.s?html?$")
# 列表页样式
_LISTY = re.compile(r"(list|index|zcwj|tzgg|xxgk|zfxxgk|/col|class|gknrz|ywwj|/zcfb|/zwgk)", re.I)


def classify_candidate(root_domain: str, list_url: str) -> str:
    h = (root_domain or "").lower()
    u = (list_url or "").lower()
    if any(j in h for j in JUNK_HOST) or u.endswith(JUNK_URL) or _ARTICLE.search(u):
        return "junk"
    if h.endswith(".gov.cn") and _LISTY.search(u):
        return "promotable"
    if h.endswith(".gov.cn"):
        return "maybe"          # gov 域但 URL 不像列表(首页兜底等)
    return "junk"


def main() -> None:
    chans = load_catalog(CAT)
    new = [c for c in chans if c.channel_type in ("商务", "市监")]   # 本次新发现
    ver = [c for c in new if c.status.value == "验证"]
    cand = [c for c in new if c.status.value == "候选"]
    for c in cand:
        c._cls = classify_candidate(c.root_domain, c.list_url)
    promotable = [c for c in cand if c._cls == "promotable"]
    maybe = [c for c in cand if c._cls == "maybe"]
    junk = [c for c in cand if c._cls == "junk"]

    def rows(items):
        out = ""
        for c in sorted(items, key=lambda x: (x.channel_type, x.city)):
            cls = getattr(c, "_cls", "")
            out += (f"<tr><td>{c.channel_type}</td><td>{c.city}</td>"
                    f"<td><code>{c.root_domain}</code></td>"
                    f"<td class='u'><a href='{c.list_url}'>{c.list_url}</a></td>"
                    f"<td>{cls}</td></tr>")
        return out

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>商务/市监渠道发现 CHECKPOINT</title>
<style>body{{font-family:system-ui;margin:2em;max-width:1200px}}h2{{margin-top:1.5em}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top}}
th{{background:#eee}}.u{{max-width:520px;overflow-wrap:anywhere}}code{{background:#f4f4f4;padding:1px 4px}}
.ver{{background:#e8f6e8}}.prom{{background:#fff7e0}}.junk{{color:#999}}
.box{{display:inline-block;border:1px solid #ccc;border-radius:6px;padding:8px 14px;margin:4px}}</style></head><body>
<h1>商务/市监渠道发现 — CHECKPOINT(2026-06-08)</h1>
<p>共发现 <b>{len(new)}</b> 个新渠道。<span class="box">验证 <b>{len(ver)}</b>(直接进 backfill)</span>
<span class="box">候选 promotable <b>{len(promotable)}</b></span>
<span class="box">候选 maybe <b>{len(maybe)}</b></span>
<span class="box junk">候选 junk <b>{len(junk)}</b></span></p>
<p>验证按 channel_type:{dict(Counter(c.channel_type for c in ver))} ·
候选按 channel_type:{dict(Counter(c.channel_type for c in cand))}</p>

<h2>① 验证 {len(ver)}(域名+机构核验都过 → 直接 backfill)</h2>
<table><tr><th>类</th><th>机构</th><th>域名</th><th>列表页 URL</th><th></th></tr>{rows(ver)}</table>

<h2>② 候选·promotable {len(promotable)}(gov域+列表页样URL,多为真商务/市监站但标记没覆盖/probe偶失 → 建议提升)</h2>
<table><tr><th>类</th><th>机构</th><th>域名</th><th>列表页 URL</th><th>判</th></tr>{rows(promotable)}</table>

<h2>③ 候选·maybe {len(maybe)}(gov域但URL不像列表页,多是首页兜底 → 需人工看)</h2>
<table><tr><th>类</th><th>机构</th><th>域名</th><th>URL</th><th>判</th></tr>{rows(maybe)}</table>

<h2>④ 候选·junk {len(junk)}(附件/单篇/oss → 丢弃,该机构这次没采到真列表页)</h2>
<table><tr><th>类</th><th>机构</th><th>域名</th><th>URL</th><th>判</th></tr>{rows(junk)}</table>
</body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"[checkpoint] → {OUT}")
    print(f"验证 {len(ver)} | promotable {len(promotable)} | maybe {len(maybe)} | junk {len(junk)}")
    print("\n--- promotable 候选(建议提升) ---")
    for c in sorted(promotable, key=lambda x: (x.channel_type, x.city)):
        print(f"  {c.channel_type} {c.city:14s} {c.root_domain:28s} {c.list_url[:70]}")
    print("\n--- maybe 候选(人工看) ---")
    for c in sorted(maybe, key=lambda x: (x.channel_type, x.city)):
        print(f"  {c.channel_type} {c.city:14s} {c.root_domain:28s} {c.list_url[:70]}")


if __name__ == "__main__":
    main()
