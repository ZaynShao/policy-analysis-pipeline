import json
from scripts.common.llm import LLMClient

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
