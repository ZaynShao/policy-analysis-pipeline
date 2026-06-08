"""从 env 构建质量门 judge client(deepseek-flash)。无 env → None(逻辑层 fallback)。"""
from __future__ import annotations
import os
from typing import Callable, Optional


def make_judge_client() -> Optional[Callable]:
    base = os.environ.get("OPENAI_BASE_URL")
    key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("JUDGE_MODEL", "deepseek-v4-flash")
    if not (base and key):
        return None
    from scripts.common.llm import OpenAICompatClient
    return OpenAICompatClient(model=model, log_path="state/l1_gate/gate_calls.jsonl",
                              base_url=base, api_key=key).complete
