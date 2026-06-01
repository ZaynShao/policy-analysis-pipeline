import json
from scripts.common.llm import LLMClient, OpenAICompatClient

class _FakeMessages:
    def create(self, **kw):
        class R:  # 模拟 anthropic 响应
            content = [type("B", (), {"text": "POLICY"})()]
        return R()

class _FakeAnthropic:
    def __init__(self, **kw): self.messages = _FakeMessages()

def test_complete_returns_text_and_logs(tmp_path):
    log = tmp_path / "llm_calls.jsonl"
    c = LLMClient(client=_FakeAnthropic(), model="m-test", log_path=str(log))
    out = c.complete("sys", "user")
    assert out == "POLICY"
    line = json.loads(log.read_text().strip())
    assert line["model"] == "m-test"
    assert line["temperature"] == 0
    assert "prompt_sha" in line and "ts" in line


def test_openai_compat_complete_and_log(tmp_path):
    captured = {}
    def fake_post(url, payload, api_key):
        captured["url"] = url; captured["payload"] = payload; captured["key"] = api_key
        return {"choices": [{"message": {"content": "通了"}}]}
    log = tmp_path / "calls.jsonl"
    c = OpenAICompatClient(model="qwen3.6-plus", log_path=str(log),
                           base_url="https://x/v1", api_key="k", _post=fake_post)
    out = c.complete("sys", "user", max_tokens=64)
    assert out == "通了"
    assert captured["url"] == "https://x/v1/chat/completions"
    assert captured["payload"]["model"] == "qwen3.6-plus"
    assert captured["payload"]["temperature"] == 0
    assert captured["payload"]["max_tokens"] == 64
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["payload"]["messages"][1] == {"role": "user", "content": "user"}
    assert captured["key"] == "k"
    line = json.loads(log.read_text().strip())
    assert line["model"] == "qwen3.6-plus" and line["output_chars"] == 2
