"""
轻量精度试探 — 8 类关系各随机抽 5 条 + 拼接政策标题,供主 session 手检。

本脚本不是正式 T4 抽样审计(T4 各类 30-50 条)。本脚本的目的是 T1 启动前
2 小时验证 L2 派生没有系统性塌方,确认 T1 跑完后 L2 流水线值得在新数据上跑。

产物:
  state/probes/2026-05-18_relations_quick/samples.jsonl  机读
  state/probes/2026-05-18_relations_quick/samples.md     人读手检版

LESSONS:
  - C5 数字脚本生成(本脚本)
  - D4 LLM 派生产物入库走同一 deterministic 脚本 → 本脚本不入库,只抽样
  - 抽样种子固定,可重现
"""
from __future__ import annotations
import json
import random
import re
from pathlib import Path

SEED = 20260518
SAMPLE_PER_CLASS = 5

VAULT = Path.home() / "Documents" / "Zayn Main" / "政策分析"
RELATIONS_DIR = VAULT / "1_extracted" / "relations"
POLICIES_DIR = VAULT / "0_raw" / "policies"
OUT_DIR = Path(__file__).resolve().parents[2] / "state" / "probes" / "2026-05-18_relations_quick"

REL_FILES = [
    "supersedes.jsonl",
    "iterates.jsonl",
    "extends.jsonl",
    "clarifies.jsonl",
    "references.jsonl",
    "aligns_with.jsonl",
    "cites_basis.jsonl",
    "derives_from.jsonl",
]


def build_pid_index() -> dict[str, dict]:
    """扫一遍 0_raw/policies,建 pid → {title, official_number, file} 索引。
    pid 来自 frontmatter 的 id 字段;aliases 字段里的旧 id 也建条目指向同一文件。
    """
    idx: dict[str, dict] = {}
    fm_re = re.compile(r"^---\n(.*?)\n---", re.S)
    for f in POLICIES_DIR.glob("*.md"):
        try:
            head = f.read_text(encoding="utf-8", errors="ignore")[:4000]
        except Exception:
            continue
        m = fm_re.search(head)
        if not m:
            continue
        fm = m.group(1)
        pid_m = re.search(r"^id:\s*(\S+)", fm, re.M)
        title_m = re.search(r"^title:\s*(.+)$", fm, re.M)
        offnum_m = re.search(r"^official_number:\s*(.+)$", fm, re.M)
        level_m = re.search(r"  level:\s*(\S+)", fm)
        date_m = re.search(r"^date:\s*['\"]?(\S+?)['\"]?\s*$", fm, re.M)
        if not pid_m:
            continue
        entry = {
            "pid": pid_m.group(1).strip(),
            "title": (title_m.group(1).strip().strip("'\"") if title_m else ""),
            "official_number": (offnum_m.group(1).strip().strip("'\"") if offnum_m else ""),
            "level": level_m.group(1).strip() if level_m else "",
            "date": date_m.group(1).strip() if date_m else "",
            "file": f.name,
        }
        idx[entry["pid"]] = entry
        # aliases:抓后续若干行直到下一个顶级键
        ali_block = re.search(r"^aliases:\n((?:  -.*\n)+)", fm, re.M)
        if ali_block:
            for line in ali_block.group(1).splitlines():
                alias = line.strip().lstrip("-").strip()
                if alias and alias != entry["pid"]:
                    idx.setdefault(alias, entry)
    return idx


def sample_class(path: Path, n: int, rng: random.Random) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) <= n:
        return rows
    return rng.sample(rows, n)


def fmt_pol(pid: str, idx: dict[str, dict]) -> str:
    e = idx.get(pid)
    if not e:
        return f"{pid}  [NOT FOUND in 0_raw/policies/]"
    bits = [e["pid"]]
    if e["pid"] != pid:
        bits.append(f"(via alias from {pid})")
    bits.append(f"[{e['level']}]" if e["level"] else "")
    bits.append(e["date"] or "")
    bits.append(e["title"])
    if e["official_number"]:
        bits.append(f"({e['official_number']})")
    return "  ".join(b for b in bits if b)


def main() -> None:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building pid index...", flush=True)
    pid_idx = build_pid_index()
    print(f"  indexed {len(pid_idx)} pid/alias entries", flush=True)

    jsonl_out = OUT_DIR / "samples.jsonl"
    md_out = OUT_DIR / "samples.md"

    all_samples = []
    md_lines = [
        "# L2 Relations 轻量精度试探 — 2026-05-18",
        "",
        f"- seed: {SEED}",
        f"- 每类抽样: {SAMPLE_PER_CLASS}",
        f"- 抽样自: `1_extracted/relations/*.jsonl`(v post-T3)",
        "- 目的: T1 启动前 2 小时,验证 L2 派生没有系统性塌方",
        "",
        "---",
        "",
    ]

    for fn in REL_FILES:
        path = RELATIONS_DIR / fn
        if not path.exists():
            md_lines.append(f"## {fn} — FILE MISSING\n")
            continue
        rel = fn[:-6]  # strip .jsonl
        samples = sample_class(path, SAMPLE_PER_CLASS, rng)
        total = sum(1 for _ in path.open(encoding="utf-8"))
        md_lines.append(f"## {rel}  (sampled {len(samples)} of {total})")
        md_lines.append("")
        for i, row in enumerate(samples, 1):
            row["_rel_file"] = fn
            all_samples.append(row)
            md_lines.append(f"### [{rel} #{i}]  confidence={row.get('confidence', '?')}")
            md_lines.append("")
            md_lines.append(f"- **from**: {fmt_pol(row.get('from', ''), pid_idx)}")
            md_lines.append(f"- **to**  : {fmt_pol(row.get('to', '') or '', pid_idx)}")
            ev = row.get("evidence", "") or ""
            if ev:
                ev_disp = ev if len(ev) <= 400 else ev[:400] + "..."
                md_lines.append(f"- **evidence**: {ev_disp}")
            reason = row.get("reason", "")
            if reason:
                md_lines.append(f"- **reason**: {reason}")
            extra = {k: v for k, v in row.items() if k not in (
                "from", "to", "rel", "evidence", "reason", "confidence",
                "extracted_by", "extracted_at", "_rel_file",
            )}
            if extra:
                md_lines.append(f"- **extra**: `{json.dumps(extra, ensure_ascii=False)}`")
            md_lines.append(f"- **extracted_by**: {row.get('extracted_by', '?')}")
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    jsonl_out.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in all_samples) + "\n",
        encoding="utf-8",
    )
    md_out.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"wrote {jsonl_out}  ({len(all_samples)} samples)")
    print(f"wrote {md_out}")


if __name__ == "__main__":
    main()
