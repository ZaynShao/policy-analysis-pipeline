"""id 前缀 issuer_short 与 issuer 字段一致性(dry-run flag,不修)。
canonical 优先(高置信),无 canonical 时回退关键字(低置信,标 source)。"""
from __future__ import annotations
from scripts.l1_audit.models import PolicyRecord, Finding

# canonical 机器码 -> issuer_short(高置信精确比对)
CANONICAL_TO_SHORT = {
    "ndrc": "NDRC", "nea": "NEA", "miit": "MIIT", "mofcom": "MOFCOM",
    "mohurd": "MOHURD", "mee": "MEE", "mof": "MOF",
    "state_council": "SC", "state_council_office": "GO", "pboc": "PBOC",
}

# 关键字回退:每个 short 要求 issuer 文本里 ALL 子串都出现(缩写容错)
SHORT_TO_KEYWORDS = {
    "NDRC": ["发展", "改革"], "NEA": ["能源"], "MIIT": ["工业", "信息"],
    "MOFCOM": ["商务"], "MOHURD": ["住房", "建设"], "MEE": ["生态", "环境"],
    "MOF": ["财政"], "SC": ["国务院"], "GO": ["国务院"], "PBOC": ["人民银行"],
}


def parse_issuer_short(pid: str) -> str:
    parts = pid.split("_")
    if len(parts) < 4:                       # 需要 P_year_short_num
        return ""
    # 去掉末尾单字母碰撞后缀(_a/_b)再解析
    if len(parts[-1]) == 1 and parts[-1].isalpha() and parts[-1].islower():
        parts = parts[:-1]
    if len(parts) < 4:
        return ""
    return "_".join(parts[2:-1])


def check_one(rec: PolicyRecord) -> Finding | None:
    short = parse_issuer_short(rec.pid)
    if not short:
        return None
    canon = rec.issuer_canonical[0].lower() if rec.issuer_canonical else ""
    # 主路径:canonical 精确比对(高置信)
    if canon in CANONICAL_TO_SHORT:
        expected = CANONICAL_TO_SHORT[canon]
        if expected == short:
            return None
        return Finding(check="id_issuer", pid=rec.pid,
                       detail={"id_short": short, "expected_short": expected,
                               "issuer_canonical": rec.issuer_canonical, "source": "canonical"},
                       proposed_action=f"id 前缀 {short} 与 canonical({canon}→{expected}) 不符 → 重算 id")
    # 回退:关键字(仅已知中央 short;低置信)
    kws = SHORT_TO_KEYWORDS.get(short)
    if kws is None:                          # 市级/未知 short → 不管
        return None
    issuer_text = " ".join(rec.issuer)
    if all(k in issuer_text for k in kws):
        return None
    return Finding(check="id_issuer", pid=rec.pid,
                   detail={"id_short": short, "issuer": rec.issuer,
                           "expected_keywords": kws, "source": "keyword"},
                   proposed_action=f"(低置信)id 前缀 {short} 与 issuer({issuer_text}) 关键字不符 → 复核")


def check_corpus(records: list[PolicyRecord]) -> list[Finding]:
    return [f for r in records if (f := check_one(r)) is not None]
