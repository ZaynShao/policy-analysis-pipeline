"""dry-run 产出:audit_report.md(人读) + proposed_changes.jsonl(机器读)。"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from dataclasses import asdict
from scripts.l1_audit.models import Finding


def write_outputs(findings: list[Finding], total_policies: int, out_dir: str) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    counts = Counter(f.check for f in findings)
    # jsonl
    with open(Path(out_dir) / "proposed_changes.jsonl", "w", encoding="utf-8") as f:
        for fd in findings:
            f.write(json.dumps(asdict(fd), ensure_ascii=False) + "\n")
    # report
    lines = ["# L1 Dry-run 审计报告", "",
             f"- 扫描政策总数: {total_policies}",
             f"- flagged 总数: {len(findings)}", "", "## 按类计数"]
    for check in ("news_release", "id_issuer", "dedup", "p1900"):
        lines.append(f"- {check}: {counts.get(check, 0)}")
    lines += ["", "## 判断型类(需抽样校 ≥95% 才自动应用)",
              "- news_release / dedup → 见 proposed_changes.jsonl,Phase 2 抽样后应用",
              "", "## 确定性类", "- id_issuer / p1900 → 人工/规则复核"]
    (Path(out_dir) / "audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
