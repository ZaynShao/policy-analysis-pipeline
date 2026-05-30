"""id 前缀 issuer_short 与 issuer 字段一致性(dry-run flag,不修)。
表 seed 自 SCHEMA §2;不在表内的 short(市级 XX_*)跳过,不误报。"""
from __future__ import annotations
from scripts.l1_audit.models import PolicyRecord, Finding

# issuer_short -> 该机构名里应出现的关键字
SHORT_TO_ISSUER_KW = {
    "NDRC": "发展和改革", "NEA": "能源局", "MIIT": "工业和信息化",
    "MOFCOM": "商务部", "MOHURD": "住房和城乡建设", "MEE": "生态环境",
    "MOF": "财政部", "SC": "国务院", "GO": "国务院办公厅", "PBOC": "中国人民银行",
}


def parse_issuer_short(pid: str) -> str:
    parts = pid.split("_")
    if len(parts) < 4:           # P_year_short_num
        return ""
    return "_".join(parts[2:-1])


def check_one(rec: PolicyRecord) -> Finding | None:
    short = parse_issuer_short(rec.pid)
    kw = SHORT_TO_ISSUER_KW.get(short)
    if kw is None:               # 市级/未知 short,本检查不管
        return None
    issuer_text = " ".join(rec.issuer)
    if kw in issuer_text:
        return None              # 一致
    return Finding(check="id_issuer", pid=rec.pid,
                   detail={"id_short": short, "issuer": rec.issuer, "expected_kw": kw},
                   proposed_action=f"id 前缀 {short} 与 issuer({issuer_text}) 不符 → 人工/重算复核")


def check_corpus(records: list[PolicyRecord]) -> list[Finding]:
    return [f for r in records if (f := check_one(r)) is not None]
