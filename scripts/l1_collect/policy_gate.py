"""L1采集质量门:heuristic预筛→LLM judge。复用 news_filter 规则,搬到采集时inline。
明显政策直通/明显非政策快拒/灰区LLM打标。低置信→review_queue(不静默丢)。"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
from typing import Callable, Optional

from .news_filter import is_news_or_press, GOV_DOMAIN_SUFFIXES

REVIEW_THRESHOLD = 0.7
POLICY_TITLE_SIGNALS = ("通知", "意见", "规定", "办法", "方案", "决定", "公告",
                        "批复", "措施", "规划", "细则", "标准", "条例", "暂行", "导则")
COMMENTARY_MARKERS = ("政策解读", "解读材料", "文字解读", "答记者问",
                      "一图读懂", "图解", "图读", "问答")
BODY_POLICY_SIGNALS = ("根据", "现就", "现将", "特此通知", "有关规定", "现通知如下")
FAST_REJECT_DOMAINS = {
    "xinhuanet.com", "people.com.cn", "cctv.com", "thepaper.cn", "sohu.com",
    "sina.com.cn", "163.com", "qq.com", "ifeng.com", "escn.com.cn",
    "in-en.com", "bjx.com.cn",
}

_SYSTEM = (
    "你是政策文档分类器。判断文档是『正式政策公文』还是非政策。只输出JSON。"
    'Schema:{"label":"policy|commentary|non_policy_index|non_policy_news|non_policy_reply",'
    '"confidence":0.0-1.0,"evidence":"<=30字"}'
)


@dataclass
class GateResult:
    ref: str
    label: str
    confidence: float
    evidence: str
    used_llm: bool
    action: str          # pass | commentary | reject | review_queue

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GoldenRecord:
    pid: str
    url: str
    title: str
    body_head: str
    gold_label: str
    is_planted: bool
    notes: str = ""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _blacklisted(url: str) -> bool:
    h = _host(url)
    return any(h == d or h.endswith("." + d) for d in FAST_REJECT_DOMAINS)


def _is_gov(url: str) -> bool:
    h = _host(url)
    return any(h.endswith(s) for s in GOV_DOMAIN_SUFFIXES)


def _heuristic(url: str, title: str, body_head: str) -> str:
    if _blacklisted(url):
        return "non_policy"
    if any(m in title for m in COMMENTARY_MARKERS):
        return "commentary"
    if _is_gov(url) and (any(s in title for s in POLICY_TITLE_SIGNALS)
                         or any(s in body_head for s in BODY_POLICY_SIGNALS)):
        return "policy"
    fr = is_news_or_press(url=url, title=title, issuer=None)
    hard = [r for r in fr.reasons if r != "issuer_unknown_but_gov_domain"]
    return "non_policy" if hard else "gray"


def gate_one(ref: str, url: str, title: str, body_head: str,
             llm_fn: Optional[Callable]) -> GateResult:
    v = _heuristic(url, title, body_head)
    if v == "commentary":
        return GateResult(ref, "commentary", 0.95, "title_commentary_marker", False, "commentary")
    if v == "policy":
        return GateResult(ref, "policy", 0.95, "heuristic_pass", False, "pass")
    if v == "non_policy":
        return GateResult(ref, "non_policy_news", 0.95, "heuristic_reject", False, "reject")
    if llm_fn is None:
        return GateResult(ref, "policy", 0.5, "llm_missing_assume_pass", False, "pass")
    user = f"标题:{title}\nURL:{url}\n正文开头:{body_head[:800]}"
    try:
        data = json.loads(llm_fn(_SYSTEM, user))
    except (json.JSONDecodeError, TypeError, ValueError):
        return GateResult(ref, "policy", 0.4, "llm_parse_error", True, "review_queue")
    label = data.get("label", "policy")
    conf = float(data.get("confidence", 0.5))
    ev = data.get("evidence", "")
    if label == "commentary":
        action = "commentary"
    elif label == "policy":
        action = "pass"
    elif conf < REVIEW_THRESHOLD:
        action = "review_queue"
    else:
        action = "reject"
    return GateResult(ref, label, conf, ev, True, action)


def gate_corpus(records: list, llm_fn: Callable) -> list:
    return [gate_one(r.pid, r.url, r.title, r.body_head, llm_fn) for r in records]
