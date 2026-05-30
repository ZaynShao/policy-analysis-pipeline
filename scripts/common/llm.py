"""最小 Claude client。temperature=0；每次调用写日志(LESSONS A5)。
真跑时从环境读 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL(中国代理)。"""
from __future__ import annotations
import os, json, hashlib, datetime
from pathlib import Path

DEFAULT_MODEL = "claude-opus-4-7"

class LLMClient:
    def __init__(self, client=None, model: str = DEFAULT_MODEL,
                 log_path: str = "state/source_ready/llm_calls.jsonl"):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
            )
        self._client = client
        self.model = model
        self.log_path = log_path

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self._client.messages.create(
            model=self.model, max_tokens=max_tokens, temperature=0,
            system=system, messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content)
        self._log(system, user, text)
        return text

    def _log(self, system: str, user: str, output: str) -> None:
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": self.model, "temperature": 0,
            "prompt_sha": hashlib.sha1((system + "\x00" + user).encode()).hexdigest()[:16],
            "output_chars": len(output),
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
