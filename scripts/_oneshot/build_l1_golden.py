"""L1 gate golden v1（修正版）。

plan 原脚本 3 处 bug，controller(4.8)已修：
  ① frontmatter 是 YAML（非 markdown #标题）→ 原 `_fields` 抓到 body 的「## 政策原文」当 title、
     lines[8:28] 抓到的是 frontmatter 不是正文。改为 yaml 解析 title+provenance.url、正文取「## 政策原文」后。
  ② vault 文件名是 title+hash（非 {pid}.md）→ 原 `POL/f"{pid}.md"` 全不存在、非政策样本=0。
     改为扫 frontmatter 建 id→path 索引。
  ③ planted 双向翻转（5好→谎称非政策/5坏→谎称政策）会让真政策被算成 recall miss、量错。
     改为清晰单向：非政策 = must-reject 测试集；planted = 其中「最像政策的灰区」。

非政策来源 = b7 污染（state/node3c/.../b7_contamination.jsonl，仅 title+marker）。
controller 人工裁决去假阳性（#18 标题抽取失败=真政策残骸 / #3,4,24,36,37,56,57 人工标注存疑边界）。
"""
from __future__ import annotations
import json
import random
import re
from pathlib import Path
import yaml

VAULT = Path.home() / "Documents/Zayn Main/政策分析"
POL = VAULT / "0_raw/policies"
B7 = Path("state/node3c/sem_preview_20260606/b7_contamination.jsonl")
OUT = Path("state/l1_gate/golden")
OUT.mkdir(parents=True, exist_ok=True)
random.seed(42)

# controller(4.8)读全文确认：这 2 个 vault 文件是新闻/工作信息（旧管线污染，body 开头「记者…获悉」、
# 源 URL 为 jjxx/wndt 动态栏目），非政策。gate 校准时正确识别为非政策 → 修正 gold 标签使冻结集诚实，
# 并入 Task12「退残留非政策」候选。
KNOWN_CONTAMINANT_PIDS = {"P_2024_HE_8b8b5a46", "P_2020_LN_e3ff353a"}

# planted=最像政策的灰区（政策解读/答复函/实施细则地方答复/答记者问/政策问答）——公平测便宜模型会不会误判
PLANTED_IDX = [13, 17, 22, 25, 26, 29, 31, 40, 44, 48]
# 另 15 条明确非政策（新闻/成效/工作推进/答复建议/法规网）——清晰 reject
CLEAR_IDX = [0, 1, 2, 5, 6, 7, 8, 9, 27, 28, 32, 39, 49, 51, 55]
NONPOLICY_IDX = PLANTED_IDX + CLEAR_IDX  # 25 条，无重叠


def _read_head(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def _pid_of(text: str) -> str:
    m = re.search(r"^id:\s*(\S+)", text[:400], re.M)
    return m.group(1).strip() if m else ""


def index_id_to_path() -> dict:
    idx = {}
    for p in POL.glob("*.md"):
        if p.name.startswith("_"):
            continue
        pid = _pid_of(_read_head(p))
        if pid:
            idx[pid] = p
    return idx


def policy_fields(p: Path) -> tuple:
    """→ (pid, title, url, body_head[:700])。"""
    txt = _read_head(p)
    m = re.search(r"^---\n(.*?)\n---", txt, re.S)
    fm = yaml.safe_load(m.group(1)) if m else {}
    fm = fm if isinstance(fm, dict) else {}
    pid = (fm.get("id") or _pid_of(txt) or p.stem).strip()
    title = str(fm.get("title") or p.stem).strip()
    url = str((fm.get("provenance") or {}).get("url") or "").strip()
    rest = txt[m.end():] if m else txt
    body = rest.split("## 政策原文", 1)[-1] if "## 政策原文" in rest else rest
    body = re.sub(r"^#+\s*", "", body.strip())
    return pid, title, url, body[:700]


def main() -> None:
    idx = index_id_to_path()
    b7 = [json.loads(l) for l in B7.read_text().splitlines() if l.strip()]
    b7_pids = {r["pid"] for r in b7}
    b7_paths = {idx[pid] for pid in b7_pids if pid in idx}

    # 好政策 25：size>2500，排除 b7 已知非政策残骸
    good = [p for p in POL.glob("*.md")
            if not p.name.startswith("_") and p.stat().st_size > 2500 and p not in b7_paths]
    sg = random.sample(good, 25)

    recs = []
    for p in sg:
        pid, title, url, body = policy_fields(p)
        if pid in KNOWN_CONTAMINANT_PIDS:
            recs.append({"pid": pid, "url": url, "title": title, "body_head": body,
                         "gold_label": "non_policy", "is_planted": False,
                         "notes": "vault_contamination_caught_by_gate"})
        else:
            recs.append({"pid": pid, "url": url, "title": title, "body_head": body,
                         "gold_label": "policy", "is_planted": False, "notes": "vault_real_policy"})

    # 非政策 25：b7 干净集；在 vault 有真文件的取真 url+body，否则 title-only
    real_url_cnt = 0
    for i in NONPOLICY_IDX:
        r = b7[i]
        pid, title = r["pid"], r["title"]
        url, body = "", ""
        if pid in idx:
            _, _, url, body = policy_fields(idx[pid])
            real_url_cnt += 1
        recs.append({"pid": pid, "url": url, "title": title, "body_head": body,
                     "gold_label": "non_policy", "is_planted": (i in PLANTED_IDX),
                     "notes": f"b7:{r['marker'][:20]}"})

    out = OUT / "golden_v1.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    n_plant = sum(r["is_planted"] for r in recs)
    n_pol = sum(r["gold_label"] == "policy" for r in recs)
    print(f"golden {len(recs)} (policy={n_pol} non_policy={len(recs) - n_pol} "
          f"planted={n_plant} 非政策含真url+body={real_url_cnt}) → {out}")


if __name__ == "__main__":
    main()
