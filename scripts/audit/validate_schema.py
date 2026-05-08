#!/usr/bin/env python3
"""
SCHEMA 契约验证器(L1 骨架第一脚本)

读 vault 抽样,校验当前 vault 内的实际数据是否符合 SCHEMA.md 约定。
不写 vault,不写派生,只读审计。

跑通这个脚本 = 证明 schema 契约能 work,pipeline ↔ vault 解耦成立。

用法:
    python3 scripts/audit/validate_schema.py
    python3 scripts/audit/validate_schema.py --vault /path/to/vault
    python3 scripts/audit/validate_schema.py --sample 50          # 抽样 50 篇
    python3 scripts/audit/validate_schema.py --strict             # 任何违反即非零退出
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

DEFAULT_VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"

# Policy frontmatter 白名单(SCHEMA §2 + §F drift register)
POLICY_FM_ALLOWED = {
    "id", "aliases", "title", "official_number", "issuer", "date",
    "region", "provenance", "issuer_canonical", "type", "subtype",
    "dup_aliases", "dedup_at", "dedup_rule", "_duplicate_of", "_duplicate_reason",
    # legacy 字段(§F drift register)
    "confidence",
}
# 已知 legacy drift,不阻塞但报告
POLICY_FM_LEGACY_DRIFT = {"tags", "classification"}
POLICY_FM_REQUIRED = {"id", "title", "date", "region", "provenance"}

# Policy body 禁止段(SCHEMA §2)
POLICY_BODY_FORBIDDEN_SECTIONS = [
    "## 摘要",
    "## 初步影响分析",
    "## 六维评分",
    "## 业务关联",
    "## 跟进建议",
    "## 战略地位映射",
]

# Commentary frontmatter 白名单(SCHEMA §3 + §F drift register)
COMMENTARY_FM_ALLOWED = {
    "title", "source_account", "source_url", "date_published", "fetched_at",
    "commentary_type", "business_tag", "source", "confidence",
    "related_policy", "related_policy_source", "not_policy_related",  # 关系字段例外
    # legacy 字段(§F drift register)
    "type", "source_type", "provenance",
    "related_policy_confidence", "related_policy_matched_at",
}
COMMENTARY_FM_REQUIRED = {"title"}

# Business view yaml(SCHEMA §4)
BUSINESS_VIEW_REQUIRED = {"pid", "scores", "extracted_at"}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """简易 frontmatter 解析。返回 (fm dict, body)。"""
    if not text.startswith("---\n"):
        return {}, text
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 5:]

    # 极简 yaml 解析(只取 top-level keys,够本契约校验用)
    fm = {}
    current_key = None
    for line in fm_text.split("\n"):
        if not line.strip():
            continue
        if line.startswith(" ") or line.startswith("\t") or line.startswith("-"):
            # 嵌套或 list 元素,挂到 current_key
            if current_key:
                if fm.get(current_key) is None:
                    fm[current_key] = []
                if isinstance(fm[current_key], list):
                    fm[current_key].append(line.strip())
            continue
        m = re.match(r"^([\w_]+)\s*:\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2)
            if val == "" or val.startswith("#"):
                fm[key] = None  # 占位,后续 list/dict 补
                current_key = key
            else:
                fm[key] = val.strip()
                current_key = key
    return fm, body


def check_policy(p: Path) -> tuple[list[str], list[str]]:
    """检查单个 policy raw 文件,返回 (violations, legacy_drifts)。"""
    violations, drifts = [], []
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return [f"{p.name}: 读取失败 {e}"], []

    fm, body = parse_frontmatter(text)

    # 必填字段
    missing = POLICY_FM_REQUIRED - set(fm.keys())
    if missing:
        violations.append(f"{p.name}: 缺必填字段 {missing}")

    # 白名单 — 区分 hard violation 与 legacy drift
    extra = set(fm.keys()) - POLICY_FM_ALLOWED
    legacy = extra & POLICY_FM_LEGACY_DRIFT
    hard = extra - POLICY_FM_LEGACY_DRIFT
    if hard:
        violations.append(f"{p.name}: 非白名单字段 {hard}")
    if legacy:
        drifts.append(f"{p.name}: legacy drift {legacy}")

    # body 禁止段
    for section in POLICY_BODY_FORBIDDEN_SECTIONS:
        if section in body:
            violations.append(f"{p.name}: body 含禁止段 {section!r}")

    return violations, drifts


def check_commentary(p: Path) -> tuple[list[str], list[str]]:
    violations, drifts = [], []
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return [f"{p.name}: 读取失败 {e}"], []

    fm, _ = parse_frontmatter(text)

    missing = COMMENTARY_FM_REQUIRED - set(fm.keys())
    if missing:
        # title 缺失是 legacy drift(已知 ~67/283),不阻塞
        if missing == {"title"}:
            drifts.append(f"{p.name}: legacy drift 缺 title")
        else:
            violations.append(f"{p.name}: 缺必填字段 {missing}")

    extra = set(fm.keys()) - COMMENTARY_FM_ALLOWED
    # policy-style 字段是 reclassified-from-policy 的 legacy drift
    legacy_policy_fields = {
        "id", "region", "issuer", "issuer_canonical", "official_number",
        "tags", "_migrated_from", "_migrated_at", "_review_needed_related_policy",
    }
    legacy = extra & legacy_policy_fields
    hard = extra - legacy_policy_fields
    if hard:
        violations.append(f"{p.name}: 非白名单字段 {hard}")
    if legacy:
        drifts.append(f"{p.name}: legacy drift (reclassified from policy) {legacy}")

    return violations, drifts


def check_business_view(p: Path) -> tuple[list[str], list[str]]:
    violations = []
    drifts = []
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return [f"{p.name}: 读取失败 {e}"]

    # business_view 是顶层 yaml,无 frontmatter dashes
    fm = {}
    current_key = None
    for line in text.split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith(" ") or line.startswith("\t") or line.startswith("-"):
            continue
        m = re.match(r"^([\w_]+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2)

    missing = BUSINESS_VIEW_REQUIRED - set(fm.keys())
    if missing:
        violations.append(f"{p.name}: 缺必填字段 {missing}")

    return violations, drifts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--sample", type=int, default=0,
                    help="抽样数,0 = 全量")
    ap.add_argument("--strict", action="store_true",
                    help="任何违反即退出码 1")
    args = ap.parse_args()

    vault = args.vault
    if not vault.exists():
        print(f"FATAL: vault 路径不存在 {vault}", file=sys.stderr)
        sys.exit(2)

    print(f"vault: {vault}")
    print(f"模式: {'抽样 ' + str(args.sample) if args.sample else '全量'}")
    print()

    violations = defaultdict(list)
    drifts = defaultdict(list)
    counts = defaultdict(int)

    # Policies
    policies = sorted((vault / "0_raw" / "policies").glob("*.md"))
    if args.sample:
        import random
        random.seed(42)
        policies = random.sample(policies, min(args.sample, len(policies)))
    counts["policies_total"] = len(list((vault / "0_raw" / "policies").glob("*.md")))
    counts["policies_checked"] = len(policies)

    for p in policies:
        v, d = check_policy(p)
        violations["policy"].extend(v)
        drifts["policy"].extend(d)

    # Commentaries
    commentaries = sorted((vault / "0_raw" / "commentaries").glob("*.md"))
    if args.sample:
        commentaries = commentaries[:args.sample]
    counts["commentaries_total"] = len(list((vault / "0_raw" / "commentaries").glob("*.md")))
    counts["commentaries_checked"] = len(commentaries)

    for c in commentaries:
        v, d = check_commentary(c)
        violations["commentary"].extend(v)
        drifts["commentary"].extend(d)

    # Business view
    bv_files = sorted((vault / "_meta" / "business_view").glob("*.yaml"))
    if args.sample:
        bv_files = bv_files[:args.sample]
    counts["business_view_total"] = len(list((vault / "_meta" / "business_view").glob("*.yaml")))
    counts["business_view_checked"] = len(bv_files)

    for b in bv_files:
        v, d = check_business_view(b)
        violations["business_view"].extend(v)
        drifts["business_view"].extend(d)

    # 报告
    print("=" * 60)
    print("规模:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print()

    total_violations = sum(len(v) for v in violations.values())
    total_drifts = sum(len(d) for d in drifts.values())

    print(f"== 严格违反 (hard violation): {total_violations} 条 ==")
    for layer, vs in violations.items():
        if vs:
            print(f"  [{layer}] {len(vs)} 条")
            for v in vs[:5]:
                print(f"    - {v}")
            if len(vs) > 5:
                print(f"    ... 还有 {len(vs) - 5} 条")

    print()
    print(f"== Legacy drift (已知,SCHEMA §F 已记录): {total_drifts} 条 ==")
    for layer, ds in drifts.items():
        if ds:
            print(f"  [{layer}] {len(ds)} 条")
            for d in ds[:3]:
                print(f"    - {d}")
            if len(ds) > 3:
                print(f"    ... 还有 {len(ds) - 3} 条")

    print()
    print("=" * 60)
    if total_violations == 0:
        if total_drifts == 0:
            print("✓ vault 100% 符合 SCHEMA 契约(无 drift)")
        else:
            print(f"✓ vault 符合 SCHEMA 契约({total_drifts} 条 legacy drift 待 cleanup pass)")
        return 0
    else:
        print(f"✗ 严格违反 {total_violations} 条")
        return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
