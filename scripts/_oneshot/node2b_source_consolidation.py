#!/usr/bin/env python3
"""② 源头收口 pass · Phase 1+2:动 vault raw(送葬非政策 + 迁评论 + GC 孤儿 bv)。

为什么:③-C 暴露 65 个非政策端点混入 raw(L1错采、②-B放大)。经重核:
  - 58 篇确凿非政策(人大政协答复/提案/解读/新闻稿/座谈/FAQ)→ 退役归档
  - 4 篇政策解读/学习文(B3)→ 迁出 policies/(commentaries 暂存,id 体系重整 defer)
  - 6 篇真政策(救回的国家级实施意见/调价通知/征求意见公告/抽取失败待修)→ 保留不动
退役+迁出后,其残留 business_view + 汕尾孤儿 → GC(纪律C:bv 无对应 raw 即删)。

⚠ KEEP/MIGRATE/退役名单 = 本 pass 人核钉快照(类比 golden),非流水线规则。
⚠ 只移动不删除 raw(归档可逆);bv 是派生层,删了可由 ②-B 重生。
用法:dry-run(默认打印不动) / apply(执行)。
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path

VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
POLICIES = VAULT / "0_raw" / "policies"
BV = VAULT / "_meta" / "business_view"
B7 = Path("state/node3c/sem_preview_20260606/b7_contamination.jsonl")
STAMP = "2026-06-06"
ARCHIVE = VAULT / "0_raw" / "_archive" / "policies" / f"b7_nonpolicy_{STAMP}"
COMM_MIG = VAULT / "0_raw" / "commentaries" / f"_migrated_from_policies_{STAMP}"

# 保留(不退役·真政策/待修)——本 pass 人核钉快照
KEEP = {
    "P_2025_GO_1201e389", "P_2022_HE_182d4944", "P_2023_SH_d77eb078",
    "P_2025_GD_1e47cd63", "P_2025_GD_badbf18f", "P_2026_SD_c4343e1d",
}
# B3:政策解读/学习文,迁出 policies/(按 hash 认,防 ②-A 改过前缀)
B3_HASHES = {"0718bc02", "6258c339", "ecd2931e", "87ca9043"}


def pid_hash(pid: str) -> str:
    return pid.rsplit("_", 1)[-1]


def scan_raw_ids() -> dict:
    """pid -> filepath，读 frontmatter id 行。"""
    m = {}
    for f in POLICIES.glob("*.md"):
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines()[:15]:
            s = line.strip()
            if s.startswith("id:"):
                m[s.split(":", 1)[1].strip()] = f
                break
    return m


def main(apply: bool):
    b7 = [json.loads(l) for l in B7.read_text(encoding="utf-8").splitlines() if l.strip()]
    retire_pids = [r["pid"] for r in b7 if r["pid"] not in KEEP and pid_hash(r["pid"]) not in B3_HASHES]
    raw = scan_raw_ids()
    raw_pids = set(raw)

    # 定位退役篇
    retire_found = [(p, raw[p]) for p in retire_pids if p in raw]
    retire_missing = [p for p in retire_pids if p not in raw]
    # 定位 B3(按 hash)
    b3_found = [(p, f) for p, f in raw.items() if pid_hash(p) in B3_HASHES]
    b3_pids = {p for p, _ in b3_found}

    # GC 预测:退役+迁出后,哪些 bv 会变孤儿(pid 不在剩余 raw)
    leaving = set(retire_pids) | b3_pids
    remaining_after = raw_pids - leaving
    bv_pids = {f.stem for f in BV.glob("*.yaml")}
    bv_orphans = sorted(bv_pids - remaining_after)  # 含汕尾既有孤儿

    print(f"=== {'APPLY' if apply else 'DRY-RUN'} ② 源头收口 Phase1+2 ===")
    print(f"raw 现有 {len(raw)} 篇")
    print(f"退役: 名单 {len(retire_pids)} · 定位到 {len(retire_found)} · 缺失 {len(retire_missing)} {retire_missing or ''}")
    print(f"B3迁出: hash {len(B3_HASHES)} 个 → 定位到 {len(b3_found)} 篇 {sorted(b3_pids)}")
    print(f"移出后 raw 余 {len(remaining_after)} 篇")
    print(f"GC 孤儿 business_view: {len(bv_orphans)} 个(含已退役/迁出的残留 + 汕尾孤儿)")

    if not apply:
        print("\n(dry-run,未动任何文件。确认后加 apply 执行)")
        return

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    COMM_MIG.mkdir(parents=True, exist_ok=True)
    log = []
    for p, f in retire_found:
        dst = ARCHIVE / f.name
        shutil.move(str(f), str(dst))
        log.append({"action": "retire_nonpolicy", "pid": p, "dst": str(dst.relative_to(VAULT)), "at": STAMP})
    for p, f in b3_found:
        dst = COMM_MIG / f.name
        shutil.move(str(f), str(dst))
        log.append({"action": "migrate_b3_commentary", "pid": p, "dst": str(dst.relative_to(VAULT)), "at": STAMP})
    # GC 孤儿 bv
    gc = 0
    for p in bv_orphans:
        y = BV / f"{p}.yaml"
        if y.exists():
            y.unlink(); gc += 1
            log.append({"action": "gc_orphan_bv", "pid": p, "at": STAMP})

    (ARCHIVE / "README.md").write_text(
        f"# b7 非政策退役 {STAMP}\n\n"
        f"③-C 关系层暴露的非政策端点(L1错采、②-B放大),经人核重核后退役。\n"
        f"退役 {len(retire_found)} 篇:人大政协答复/提案/建议、政策解读/问答/访谈、"
        f"新闻稿/动态/座谈/框架协议/报告、门户FAQ。\n"
        f"判据=triage NONPOLICY 通则 + 人核(详见 pipeline state/node3c/.../retire_list.jsonl + 收口报告)。\n"
        f"保留未退的 6 篇真政策见 keep_in_raw_list.jsonl。移动可逆。\n", encoding="utf-8")
    (COMM_MIG / "README.md").write_text(
        f"# B3 政策解读/学习文迁出 {STAMP}\n\n"
        f"4 篇政策解读/学习文误入 0_raw/policies/,迁出至此(脱离 policies 使 ②-B 不再当政策挂theme)。\n"
        f"commentary id 体系重整 = BACKLOG B3 后续(此处仅暂存留痕)。\n", encoding="utf-8")
    logf = VAULT / "0_raw" / "_archive" / f"apply_log_b7_{STAMP}.jsonl"
    with logf.open("w", encoding="utf-8") as fh:
        for r in log:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n✅ 退役 {len(retire_found)} · B3迁出 {len(b3_found)} · GC孤儿bv {gc}")
    print(f"   log → {logf.relative_to(VAULT)}")
    print(f"   raw 现 {len(list(POLICIES.glob('*.md')))} 篇 · bv 现 {len(list(BV.glob('*.yaml')))} 个")


if __name__ == "__main__":
    main(apply=(len(sys.argv) > 1 and sys.argv[1] == "apply"))
