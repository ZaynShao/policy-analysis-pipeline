"""Task12 收口:把 18 个官方政策解读/问答/图解/答记者问 从 0_raw/policies/ 移到
0_raw/commentaries/(用户拍:等价『政策评论』·官方解读=权威 vs wewe-rss第三方=观点)。

只动 vault 未提交(untracked)新文件里 title 命中解读标记的那批(=本会话 backfill 带进来的)。
对每篇:
  - 物理移动 policies/ → commentaries/(写新文件 + 删原文件;untracked 故无需 git mv)
  - frontmatter 加工(保留原 raw 字段 + provenance + body 逐字不动):
      type: policy → 政策评论
      + source: l1_official
      + commentary_kind: official            # 区分 wewe-rss(第三方观点)
      + business_tag: <由内容关键词派生>      # 对齐 corpus 词表 power/gas/charging/cross
      + source_url: <= provenance.url>        # 对齐 commentary corpus 查询字段
      + date_published: <= date>              # 同上
      + related_policy: [pid...]              # best-effort:从标题《X》匹配已采政策
      + related_policy_source: l1_title_match
      + related_policy_confidence: 0.7
DRY_RUN=1 只打印计划不写盘。
"""
from __future__ import annotations
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
POLICIES = VAULT / "0_raw/policies"
COMMENTARIES = VAULT / "0_raw/commentaries"
CST = timezone(timedelta(hours=8))
DRY = os.environ.get("DRY_RUN") == "1"

MARKERS = ["政策解读", "文字解读", "解读材料", "问答", "答记者问", "一图读懂", "图解", "图读"]

# business_tag 词表(corpus: power/gas/charging/cross),按优先级匹配
_TAG_RULES = [
    ("charging", ["充电", "电动汽车", "充电桩", "换电", "以旧换新", "新能源汽车"]),
    ("gas", ["成品油", "天然气", "油气", "加油", "管网", "价格联动"]),
    ("power", ["电力", "电网", "储能", "绿电", "光伏", "现货", "需求响应",
                "配电", "新型储能", "电源", "核算指南", "碳达峰", "直连"]),
]


def _front_body(txt: str):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
    if not m:
        return None, None
    fm = yaml.safe_load(m.group(1))
    if not isinstance(fm, dict):
        return None, None
    return fm, m.group(2)


def untracked_policies() -> list:
    out = subprocess.run(
        ["git", "-C", str(VAULT), "status", "--porcelain", "-z", "0_raw/policies/"],
        capture_output=True, text=True).stdout
    return [ent[3:] for ent in out.split("\0") if ent.startswith("??")]


def is_interp(title: str) -> bool:
    return any(k in title for k in MARKERS)


def derive_tag(title: str, body: str) -> str:
    # 标题优先(可靠);标题无信号才看正文(防正文串味,如碳达峰答记者问正文带"价格")
    for src in (title, (body or "")[:400]):
        for tag, kws in _TAG_RULES:
            if any(k in src for k in kws):
                return tag
    return "cross"


def _normalize(s: str) -> str:
    s = re.sub(r"[《》【】\s]", "", s)
    s = re.sub(r"（[^）]*）|\([^)]*\)", "", s)  # 去括号注(试行/年版/版本号)
    return s


def ref_policy_name(title: str) -> str:
    """从解读标题抽被解读政策名:优先《》内,否则剥前后缀标记词。"""
    m = re.search(r"《([^》]+)》", title)
    if m:
        return m.group(1)
    t = title
    for pre in ("一图读懂丨", "一图读懂 |", "一图读懂|", "一图读懂", "图解：", "图解:", "文字解读：", "文字解读:"):
        if t.startswith(pre):
            t = t[len(pre):]
    for suf in MARKERS:
        t = t.replace(suf, "")
    return t.strip("：: 　")


def build_title_index(skip_paths: set) -> list:
    """全 policies/ 标题→pid 索引(排除将移走的18篇)。返回 [(norm_title, pid, raw_title)]。"""
    idx = []
    for p in POLICIES.glob("*.md"):
        if p.name in skip_paths:
            continue
        fm, _ = _front_body(p.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        pid = fm.get("id")
        title = str(fm.get("title") or "")
        if pid and title:
            idx.append((_normalize(title), pid, title))
    return idx


def match_related(ref_name: str, index: list):
    """best-effort:被解读政策名 vs 政策标题,双向 containment,取规范化长度最接近的。"""
    nref = _normalize(ref_name)
    if len(nref) < 6:
        return None, None
    best = None
    for ntitle, pid, raw in index:
        if not ntitle:
            continue
        # 方向1 nref⊂ntitle(政策标题=「关于印发《ref》的通知」)可靠;
        # 方向2 ntitle⊂nref 仅在政策标题够长时接受(挡掉"通知"这类通用碎片假阳)
        hit = (nref in ntitle) or (ntitle in nref and len(ntitle) >= 10)
        if hit:
            score = -abs(len(ntitle) - len(nref))  # 越接近越好
            if best is None or score > best[0]:
                best = (score, pid, raw)
    if best:
        return best[1], best[2]
    return None, None


def _rel(p: Path) -> str:
    return str(p.relative_to(VAULT))


def _is_tracked(p: Path) -> bool:
    try:
        rel = _rel(p)
    except ValueError:
        return False   # 不在 VAULT 下 → 不可能被 vault git 跟踪
    r = subprocess.run(["git", "-C", str(VAULT), "ls-files", "--error-unmatch", rel],
                       capture_output=True)
    return r.returncode == 0


def route_files(paths: list, index: list, dry: bool, now: str = "") -> int:
    """转换给定文件 → commentaries/。tracked 走 git rm,untracked unlink。返回处理数(dry=True 时为满足条件数,非实际写入数)。"""
    now = now or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    n = 0
    for p in paths:
        if not p.exists():
            continue
        fm, body = _front_body(p.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        title = str(fm.get("title") or "")
        tag = derive_tag(title, body)
        pid, _ = match_related(ref_policy_name(title), index)
        prov = fm.get("provenance") or {}
        fm["type"] = "政策评论"
        fm["source"] = "l1_official"
        fm["commentary_kind"] = "official"
        fm["business_tag"] = tag
        if prov.get("url"): fm["source_url"] = prov["url"]
        if fm.get("date"): fm["date_published"] = fm["date"]
        if pid:
            fm["related_policy"] = [pid]
            fm["related_policy_source"] = "l1_title_match"
            fm["related_policy_confidence"] = 0.7
            fm["related_policy_matched_at"] = now
        n += 1
        if dry:
            continue
        new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
        (COMMENTARIES / p.name).write_text(f"---\n{new_fm}---\n{body}", encoding="utf-8")
        if _is_tracked(p):
            r = subprocess.run(["git", "-C", str(VAULT), "rm", "-q", "--", _rel(p)],
                                capture_output=True)
            if r.returncode != 0:
                raise RuntimeError(f"git rm failed for {p.name}: {r.stderr.decode(errors='ignore')[:200]}")
        else:
            p.unlink()
    return n


def main() -> None:
    files = untracked_policies()
    target_paths = []
    for fn in files:
        p = VAULT / fn
        if not p.exists():
            continue
        fm, _ = _front_body(p.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        if is_interp(str(fm.get("title") or "")):
            target_paths.append(p)
    skip = {p.name for p in target_paths}
    index = build_title_index(skip)
    print(f"untracked={len(files)}  解读={len(target_paths)}  index={len(index)}  DRY={DRY}\n")

    moved = route_files(target_paths, index, DRY)
    print(f"\n{'(dry)将移' if DRY else '已移'} {moved} 篇 → commentaries/")


if __name__ == "__main__":
    main()
