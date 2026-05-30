"""dry-run 产出:audit_report.md(人读,分层明细) + proposed_changes.jsonl(机器读)。"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from dataclasses import asdict
from scripts.l1_audit.models import Finding

def write_outputs(findings: list[Finding], total_policies: int, out_dir: str) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # jsonl(机器读,不变)
    with open(Path(out_dir) / "proposed_changes.jsonl", "w", encoding="utf-8") as f:
        for fd in findings:
            f.write(json.dumps(asdict(fd), ensure_ascii=False) + "\n")

    def of(check): return [fd for fd in findings if fd.check == check]
    counts = Counter(fd.check for fd in findings)

    L = ["# L1 Dry-run 审计报告", "",
         f"- 扫描政策总数: {total_policies}",
         f"- flagged 总数: {len(findings)}", "", "## 按类计数"]
    for c in ("news_release", "id_issuer", "dedup", "p1900"):
        L.append(f"- {c}: {counts.get(c, 0)}")

    # id_issuer 分层
    idf = of("id_issuer")
    if idf:
        src = Counter(fd.detail.get("source") for fd in idf)
        shorts = Counter(fd.detail.get("id_short") for fd in idf)
        L += ["", "## id_issuer 分层",
              f"- 高置信(canonical 实锤): {src.get('canonical', 0)}",
              f"- 低置信(keyword 线索): {src.get('keyword', 0)}",
              "- top id_short: " + ", ".join(f"{k}={v}" for k, v in shorts.most_common(8))]
        canon = [fd for fd in idf if fd.detail.get("source") == "canonical"]
        if canon:
            L.append("- 高置信明细(应优先处置):")
            for fd in canon:
                L.append(f"  - {fd.pid}: {fd.proposed_action}")

    # dedup 组明细
    ded = of("dedup")
    if ded:
        dupn = sum(len(fd.detail.get("dups", [])) for fd in ded)
        L += ["", f"## dedup({len(ded)} 组 / {dupn} 篇待去重)"]
        for fd in ded:
            L.append(f"- 留 {fd.detail.get('keep')};去 {fd.detail.get('dups')}")

    # news 候选
    nf = of("news_release")
    if nf:
        L += ["", f"## news_release 候选({len(nf)} 篇)"]
        for fd in nf:
            L.append(f"- {fd.pid}: {fd.detail.get('label')} (conf={fd.detail.get('confidence', '-')})")

    # p1900
    pf = of("p1900")
    if pf:
        L += ["", "## p1900"] + [f"- {fd.pid}" for fd in pf]

    L += ["", "## 处置纪律",
          "- news_release / dedup 判断型:抽样校 ≥95% 才自动应用",
          "- id_issuer 高置信→重算 id;低置信→人工复核;p1900→backlog"]
    (Path(out_dir) / "audit_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
