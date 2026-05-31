"""确定性抽取器:标题->发文机关、正文落款->日期。纯函数。"""
from __future__ import annotations
import re

# 机关名以这些结尾(放行单机关 + 顿号/空格分隔的联合发文)
_ORG_TAIL = "(?:办公厅|办公室|人民政府|政府|委员会|管委会|发展改革委|能源局|工业和信息化局|" \
            "工业和信息化部|商务局|商务委员会|财政局|财政厅|交通运输厅|自然资源和规划局|" \
            "市场监督管理局|委|局|厅|部|院|中心)"
# 标题前缀 = 机关名(可含 顿号/空格/、连接多机关)直到 "关于"
_TITLE_RE = re.compile(r"^([一-龥、\s]+?" + _ORG_TAIL + r")关于")

_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def extract_issuer_from_title(title: str):
    """标题 'XXX关于...的通知' -> 'XXX';无匹配 -> None。"""
    if not title:
        return None
    m = _TITLE_RE.match(title.strip())
    if not m:
        return None
    return m.group(1).strip()


def extract_luokuan_date(body_tail: str):
    """正文尾部落款中文日期 'YYYY年M月D日' -> 'YYYY-MM-DD';取最后一个(最贴近落款);无 -> None。"""
    if not body_tail:
        return None
    ms = list(_DATE_RE.finditer(body_tail))
    if not ms:
        return None
    y, mo, d = ms[-1].groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
