"""政策 vs 新闻稿:heuristic 预筛(复用 news_filter) → LLM 逐条确认 flagged。"""
from __future__ import annotations
import json
from typing import Callable
from scripts.l1_collect.news_filter import is_news_or_press
from scripts.l1_audit.models import PolicyRecord, Finding

LLMFn = Callable[[str, str], str]   # (system, user) -> raw text

_SYSTEM = (
    "你是政策文档分类器。判断给定文档是『正式政策公文』还是"
    "『新闻稿/报道/索引页/纯转载』。只输出 JSON,无解释。"
    'schema: {"label": "policy|news_release|index_page|reprint_only",'
    ' "confidence": 0-1, "evidence": "<=30字依据"}'
)


def _heuristic_flagged(rec: PolicyRecord) -> bool:
    issuer = rec.issuer[0] if rec.issuer else None
    return is_news_or_press(rec.url, rec.title, issuer).is_filtered


def classify_one(rec: PolicyRecord, llm_fn: LLMFn) -> Finding | None:
    if not _heuristic_flagged(rec):
        return None                      # 明显政策,跳过 LLM
    user = f"标题:{rec.title}\nURL:{rec.url}\n正文开头:{rec.body_head[:800]}"
    try:
        data = json.loads(llm_fn(_SYSTEM, user))
    except (json.JSONDecodeError, TypeError):
        return Finding(check="news_release", pid=rec.pid,
                       detail={"label": "unresolved"},
                       proposed_action="LLM 解析失败 → 人工清单")
    if data.get("label", "policy") == "policy":
        return None                      # LLM 平反:确是政策
    return Finding(check="news_release", pid=rec.pid, detail=data,
                   proposed_action=f"迁 _archive/policies/news_release/ ({data.get('label')})")


def classify_corpus(records: list[PolicyRecord], llm_fn: LLMFn) -> list[Finding]:
    out = []
    for r in records:
        f = classify_one(r, llm_fn)
        if f is not None:
            out.append(f)
    return out
