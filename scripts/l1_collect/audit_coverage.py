"""L1覆盖审计:省×主题矩阵+零覆盖告警+新鲜度+缺口归因+HTML。
指标LLM设计一次→固化为规则(不每次调LLM防漂移)。"""
from __future__ import annotations
import argparse
import datetime
import re
from collections import defaultdict
from pathlib import Path

VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
BV_DIR = VAULT / "_meta" / "business_view"
POLICIES_DIR = VAULT / "0_raw" / "policies"
STALE_DAYS = 60
THEMES = ["充电", "加油", "电力"]
KEY_PROVINCES = {"广东省", "江苏省", "浙江省", "山东省", "四川省", "河南省", "湖北省",
                 "湖南省", "安徽省", "河北省", "福建省", "上海市", "北京市", "重庆市"}


def compute_coverage_matrix(bv_dir: Path) -> dict:
    import yaml
    m = defaultdict(lambda: defaultdict(int))
    if not bv_dir.exists():
        return {}
    for f in bv_dir.glob("*.yaml"):
        try:
            bv = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        region = bv.get("region") or ""
        prov = region.split("/")[0].strip() if region else ""
        themes = bv.get("themes") or []
        if not prov:
            continue
        for t in THEMES:
            if any(t in th for th in themes):
                m[prov][t] += 1
    return {p: dict(v) for p, v in m.items()}


def get_zero_alerts(matrix: dict) -> list:
    out = []
    for prov in matrix:
        if prov not in KEY_PROVINCES:
            continue
        for t in THEMES:
            if matrix.get(prov, {}).get(t, 0) == 0:
                out.append({"province": prov, "theme": t, "count": 0, "severity": "HIGH"})
    return out


def diagnose_gap(province: str, theme: str, scanned_count: int) -> dict:
    cause = "collection_gap" if scanned_count == 0 else "attribution_gap"
    action = (f"补采 {province} {theme} 渠道" if cause == "collection_gap"
              else f"复查 {province} 已采政策的 region/theme 标注(回灌②)")
    return {"province": province, "theme": theme, "cause": cause, "action": action}


def compute_freshness(policies_dir: Path) -> dict:
    fresh: dict = {}
    DATE = re.compile(r"fetched_at:\s*(.+)")
    REGION = re.compile(r"^region:\s*(.+)", re.M)
    for p in policies_dir.glob("*.md"):
        try:
            c = p.read_text(encoding="utf-8")
        except Exception:
            continue
        md, mr = DATE.search(c), REGION.search(c)
        if not (md and mr):
            continue
        d = md.group(1).strip()[:10]
        prov = mr.group(1).strip().split("/")[0]
        if prov and (prov not in fresh or d > fresh[prov]):
            fresh[prov] = d
    return fresh


def check_freshness(freshness: dict, stale_days: int = STALE_DAYS) -> list:
    cutoff = (datetime.date.today() - datetime.timedelta(days=stale_days)).isoformat()
    return [{"province": p, "last_date": d, "severity": "WARN"}
            for p, d in freshness.items() if d < cutoff]


def render_html_report(matrix: dict, alerts: list, freshness: dict) -> str:
    provs = sorted(set(matrix) | set(freshness))
    cutoff = (datetime.date.today() - datetime.timedelta(days=STALE_DAYS)).isoformat()
    rows = ""
    for prov in provs:
        bold = "font-weight:bold" if prov in KEY_PROVINCES else ""
        cells = ""
        for t in THEMES:
            n = matrix.get(prov, {}).get(t, 0)
            cls = ' class="zero"' if n == 0 else ""
            cells += f'<td{cls}>{n}</td>'
        fr = freshness.get(prov, "—")
        fcls = ' style="color:red"' if fr != "—" and fr < cutoff else ""
        rows += f'<tr><td style="{bold}">{prov}</td>{cells}<td{fcls}>{fr}</td></tr>'
    alert_html = ""
    if alerts:
        lis = "".join(f"<li>[{a.get('severity','')}] {a.get('province','')} "
                      f"{a.get('theme','')}</li>" for a in alerts)
        alert_html = f"<h2>告警({len(alerts)})</h2><ul>{lis}</ul>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>L1覆盖审计</title>
<style>table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:4px 8px}}
th{{background:#eee}}.zero{{background:#fcc}}</style></head><body>
<h1>L1采集覆盖审计 — {datetime.date.today()}</h1>{alert_html}
<h2>省×主题矩阵</h2><table>
<tr><th>省</th>{''.join(f'<th>{t}</th>' for t in THEMES)}<th>最后采集</th></tr>
{rows}</table>
<p>加粗=重点省 / 红底=零覆盖 / 红字=超{STALE_DAYS}天未采</p></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="state/l1_gate/audit_coverage.html")
    a = ap.parse_args()
    matrix = compute_coverage_matrix(BV_DIR)
    fresh = compute_freshness(POLICIES_DIR)
    alerts = get_zero_alerts(matrix) + check_freshness(fresh)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html_report(matrix, alerts, fresh), encoding="utf-8")
    print(f"[audit] 省份={len(matrix)} 告警={len(alerts)} → {out}")
    for z in get_zero_alerts(matrix):
        print(f"  零覆盖 {z['province']} {z['theme']}")


if __name__ == "__main__":
    main()
