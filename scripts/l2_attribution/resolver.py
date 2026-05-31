"""resolve_identity:确定性算 identity。纯函数,零 pid 分支。"""
from __future__ import annotations
import re
from pathlib import Path
from scripts.l2_attribution.models import ResolvedIdentity
from scripts.l2_attribution.channel_registry import lookup
from scripts.l2_attribution.extractors import (
    extract_issuer_from_title, extract_luokuan_date,
)

_PLACE_RE = re.compile(r"(北京|天津|上海|重庆|[一-龥]{2,6}?[省市区县])")
_DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_THIS_YEAR = 2026  # 上限年份;跨年时更新(或改 datetime.date.today().year)


def old_hash_of(pid: str) -> str:
    """P_YYYY_PREFIX_<hash> -> <hash>(末段)。"""
    parts = (pid or "").split("_")
    return parts[-1] if parts else ""


def body_tail_of(path: str, n: int = 900) -> str:
    """读文件末尾 n 字符(落款在文末)。"""
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""
    return txt[-n:]


def _date_year(date_str: str):
    m = re.match(r"^(\d{4})", date_str or "")
    return m.group(1) if m else None


def _existing_date_ok(date_str: str) -> bool:
    if not _DATE_OK.match(date_str or ""):
        return False
    y = int(date_str[:4])
    return 1990 <= y <= _THIS_YEAR


def _alloc_id(year, issuer_short, hsh, existing_ids):
    base = f"P_{year}_{issuer_short}_{hsh}"
    if base not in existing_ids:
        return base
    for suf in "abcdefghij":
        cand = f"{base}_{suf}"
        if cand not in existing_ids:
            return cand
    return None  # 槽耗尽 → 交调用方入队列


def resolve_identity(rec, registry, body_tail: str, existing_ids: set) -> ResolvedIdentity:
    """
    existing_ids: 其它记录已占用的 id 集合;函数内部会排除 rec.pid 自身,故调用方可安全传入全量 pid 集。
    """
    ri = ResolvedIdentity(pid=rec.pid)
    entry = lookup(registry, rec.url)

    # 1) 非 gov / 不在 registry -> 整条 unknown
    if entry is None:
        ri.add_conflict("_all", reason="域名不在 channel_registry(非gov/未收录)",
                        signals={"url": rec.url})
        return ri

    # 2) region(仅域名)
    cur_region = getattr(rec, "raw_fm", {}).get("region") if hasattr(rec, "raw_fm") else None
    if cur_region != entry.region:
        ri.set_field("region", entry.region, method="domain_lookup",
                     confidence=0.99, from_val=str(cur_region))

    # 3) issuer 全名:标题抽取 + 域名背书(机关名含域名区域名之一)
    title_issuer = extract_issuer_from_title(rec.title)
    if title_issuer:
        region_name = entry.region.get("name", "")
        place = region_name.replace("省", "").replace("市", "")
        backed = (entry.region["level"] == "国家") or (place and place in title_issuer)
        if backed:
            ri.set_field("issuer", [title_issuer], method="title_extract",
                         confidence=0.95, from_val=str(getattr(rec, "issuer", "")))
            ri.set_field("issuer_canonical", [entry.issuer_canonical],
                         method="domain_lookup", confidence=0.9)
        else:
            ri.add_conflict("issuer",
                            reason="标题机关与域名区域不符(转载/联合/媒体)",
                            signals={"title_issuer": title_issuer,
                                     "domain_region": region_name})

    # 4) date:落款抽到即写;抽不到保留合法现值,否则入队列
    luokuan = extract_luokuan_date(body_tail)
    final_date = rec.date
    if luokuan:
        if luokuan != rec.date:
            ri.set_field("date", luokuan, method="body_chinese_date",
                         confidence=0.92, from_val=str(rec.date))
        final_date = luokuan
    elif not _existing_date_ok(rec.date):
        ri.add_conflict("date", reason="落款抽不到且现值坏",
                        signals={"frontmatter": rec.date, "luokuan": None})

    # 5) id:用最终 date 年 + issuer_short + 原 hash
    year = _date_year(final_date)
    if year:
        new_id = _alloc_id(year, entry.issuer_short, old_hash_of(rec.pid),
                           existing_ids - {rec.pid})
        if new_id is None:
            ri.add_conflict("id", reason="id 碰撞槽耗尽(_a.._j 全占)",
                            signals={"base": f"P_{year}_{entry.issuer_short}_{old_hash_of(rec.pid)}"})
        elif new_id != rec.pid:
            ri.set_field("id", new_id, method="id_recompute_from_metadata",
                         confidence=0.99, from_val=rec.pid)
    else:
        ri.add_conflict("id", reason="无可用年份,无法重算 id",
                        signals={"final_date": final_date})

    return ri
