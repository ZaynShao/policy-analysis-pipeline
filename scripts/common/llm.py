"""最小 LLM client。temperature=0；每次调用写日志(LESSONS A5)。
- LLMClient: Anthropic messages 接口。从环境读 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL
  (中国代理,或 Anthropic 兼容端点如 MiniMax https://api.minimaxi.com/anthropic)。
- OpenAICompatClient: OpenAI 兼容 chat/completions(如 DashScope/Qwen),同 .complete 接口。
"""
from __future__ import annotations
import os, json, hashlib, datetime
from pathlib import Path

DEFAULT_MODEL = "claude-opus-4-7"


def _log_call(log_path: str, model: str, system: str, user: str, output: str) -> None:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": model, "temperature": 0,
        "prompt_sha": hashlib.sha1((system + "\x00" + user).encode()).hexdigest()[:16],
        "output_chars": len(output),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
        # reasoning 模型(如 MiniMax-M2.7)返回 thinking 块 + text 块;只取 text。
        # ⚠ 这类模型 max_tokens 须够大覆盖"思考+输出",否则预算耗在 thinking 上→截断成空。
        text = "".join(getattr(b, "text", "") for b in resp.content)
        _log_call(self.log_path, self.model, system, user, text)
        return text


class OpenAICompatClient:
    """OpenAI 兼容 Chat Completions 客户端(如 DashScope/Qwen)。同 LLMClient 的
    .complete(system, user, max_tokens) 接口,temperature=0,写同格式日志。
    base_url/api_key 默认读 OPENAI_BASE_URL / OPENAI_API_KEY;_post 可注入(测试)。"""

    def __init__(self, model: str, log_path: str = "state/source_ready/llm_calls.jsonl",
                 base_url: str | None = None, api_key: str | None = None, _post=None):
        self.model = model
        self.log_path = log_path
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._post = _post or self._http_post

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        data = self._post(f"{self.base_url}/chat/completions", {
            "model": self.model, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, self.api_key)
        text = (data["choices"][0]["message"].get("content") or "")
        _log_call(self.log_path, self.model, system, user, text)
        return text

    @staticmethod
    def _http_post(url: str, payload: dict, api_key: str) -> dict:
        import urllib.request
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
