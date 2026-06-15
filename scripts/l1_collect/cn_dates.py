"""中文数字日期解析 + 发文日(落款)语义优先选取。纯函数,零依赖。

date 抽取的单一真相源(L1 metadata_extractor 与 L2 attribution extractors 共用):
- 识别中文数字落款(二〇二三年九月[十五日])与阿拉伯/ISO 日期。
- 按上下文剔除"生效/截止/执行起始日",只留发文/落款日。
- 缺日时按 01 补(中文落款常只到月),调用方可按需降置信。
"""
from __future__ import annotations
import re
from dataclasses import dataclass

_CN_DIGIT = {"〇": 0, "○": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_YEAR_RE = r"[〇○零一二三四五六七八九]{4}"
_CN_MD_RE = r"[一二三四五六七八九十]{1,3}"

_DATE_ARABIC = re.compile(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?")
_DATE_ISO = re.compile(r"((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})")
_DATE_CN = re.compile(rf"({_CN_YEAR_RE})年({_CN_MD_RE})月(?:({_CN_MD_RE})日)?")

# 生效:日期后接 [起]{施行|执行|生效|实施},或日期前紧邻 "自"
_EFFECTIVE_AFTER = re.compile(r"^\s*起?(?:施行|执行|生效|实施)")
# 截止:日期前出现 有效期至/有效期到/截止/截至
_DEADLINE_BEFORE = re.compile(r"(?:有效期至|有效期到|截止|截至)\s*$")


def cn_year_to_int(s: str):
    """'二〇二三' -> 2023;非 4 位中文数字 -> None。"""
    if not s or len(s) != 4:
        return None
    out = 0
    for ch in s:
        if ch not in _CN_DIGIT:
            return None
        out = out * 10 + _CN_DIGIT[ch]
    return out


def cn_md_to_int(s: str):
    """中文月/日(1..31),十-based:'十五'->15 '二十八'->28 '九'->9。无法解析 -> None。"""
    if not s:
        return None
    if s == "十":
        return 10
    if "十" in s:
        tens, _, ones = s.partition("十")
        t = _CN_DIGIT.get(tens, None) if tens else 1   # '十X' -> 1X
        o = _CN_DIGIT.get(ones, 0) if ones else 0
        if t is None or o is None:
            return None
        return t * 10 + o
    return _CN_DIGIT.get(s)


@dataclass
class DateCand:
    date: str        # YYYY-MM-DD(缺日补 01)
    has_day: bool
    start: int
    end: int
    kind: str        # effective | deadline | neutral


def _norm(y, mo, d) -> str:
    return f"{int(y):04d}-{int(mo):02d}-{int(d or 1):02d}"


def _classify(text: str, start: int, end: int) -> str:
    before = text[max(0, start - 10):start]
    after = text[end:end + 8]
    if _EFFECTIVE_AFTER.match(after):
        return "effective"
    if before.endswith("自"):
        return "effective"
    if _DEADLINE_BEFORE.search(before):
        return "deadline"
    return "neutral"


def find_date_candidates(text: str):
    """文本内全部日期候选,按出现位置排序,带生效/截止/中性分类。"""
    cands = []
    for m in _DATE_ARABIC.finditer(text):
        y, mo, d = m.groups()
        if not 1 <= int(mo) <= 12:
            continue
        if d and not 1 <= int(d) <= 31:
            continue
        cands.append(DateCand(_norm(y, mo, d), bool(d), m.start(), m.end(),
                              _classify(text, m.start(), m.end())))
    for m in _DATE_ISO.finditer(text):
        y, mo, d = m.groups()
        if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
            continue
        cands.append(DateCand(_norm(y, mo, d), True, m.start(), m.end(),
                              _classify(text, m.start(), m.end())))
    for m in _DATE_CN.finditer(text):
        yi = cn_year_to_int(m.group(1))
        mi = cn_md_to_int(m.group(2))
        di = cn_md_to_int(m.group(3)) if m.group(3) else None
        if yi is None or mi is None or not 1 <= mi <= 12:
            continue
        if di is not None and not 1 <= di <= 31:
            continue
        cands.append(DateCand(_norm(yi, mi, di), di is not None, m.start(), m.end(),
                              _classify(text, m.start(), m.end())))
    cands.sort(key=lambda c: c.start)
    return cands


def pick_issuance_date(text: str) -> str:
    """取发文/落款日:剔除生效/截止候选,落款在文末 → 取最末的中性日期。无 -> ''。"""
    if not text:
        return ""
    neutral = [c for c in find_date_candidates(text) if c.kind == "neutral"]
    return neutral[-1].date if neutral else ""


def is_effective_or_deadline_date(text: str, date_str: str) -> bool:
    """text 中 date_str 是否以生效/截止语义出现(resolver 判定存量 date 误标用)。"""
    if not text or not date_str:
        return False
    return any(c.date == date_str and c.kind in ("effective", "deadline")
               for c in find_date_candidates(text))
