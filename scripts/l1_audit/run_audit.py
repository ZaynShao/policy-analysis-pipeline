"""L1 dry-run 审计编排。零变更:只读 vault → 跑 4 类检查 → 写报告。
真跑: python3 -m scripts.l1_audit.run_audit --policies-dir <vault>/0_raw/policies"""
from __future__ import annotations
import argparse
from typing import Callable, Optional
from scripts.l1_audit.corpus import load_policies
from scripts.l1_audit.news_classifier import classify_corpus
from scripts.l1_audit.id_issuer_check import check_corpus
from scripts.l1_audit.dedup_group import group_duplicates
from scripts.l1_audit.scans import scan_p1900
from scripts.l1_audit.report import write_outputs


def run_dry_run(policies_dir: str, out_dir: str,
                llm_fn: Optional[Callable[[str, str], str]] = None) -> None:
    if llm_fn is None:
        from scripts.common.llm import LLMClient
        llm_fn = LLMClient().complete
    recs = load_policies(policies_dir)
    findings = []
    findings += classify_corpus(recs, llm_fn)
    findings += check_corpus(recs)
    findings += group_duplicates(recs)
    findings += scan_p1900(recs)
    write_outputs(findings, total_policies=len(recs), out_dir=out_dir)
    print(f"[dry-run] policies={len(recs)} findings={len(findings)} -> {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies-dir", required=True)
    ap.add_argument("--out-dir", default="state/source_ready")
    args = ap.parse_args()
    run_dry_run(args.policies_dir, args.out_dir)


if __name__ == "__main__":
    main()
