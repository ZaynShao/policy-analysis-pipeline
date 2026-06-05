from scripts.analysis_semantic_relations.judge import judge_candidate, SEMANTIC_RELATION_JUDGE_SYSTEM


class FakeClient:
    def __init__(self, payload): self.payload = payload; self.calls = []
    def complete(self, system, user, max_tokens=1024):
        self.calls.append((system, user)); return self.payload


def test_judge_parses_decision():
    c = FakeClient('{"decision":"accept","confidence":0.8,"reason":"地方落实上级且主题一致"}')
    v = judge_candidate(c, {"from": "P_L", "to": "P_N", "rel": "derives_from",
                            "evidence": {"from_title": "x", "to_title": "y"}})
    assert v.decision == "accept" and 0 <= v.confidence <= 1


def test_judge_non_json_is_manual_review():
    v = judge_candidate(FakeClient("不是JSON"), {"from": "A", "to": "B", "rel": "iterates", "evidence": {}})
    assert v.decision == "manual_review"   # 解析失败→保守进人工池(不静默 accept)


def test_prompt_forbids_free_association():
    assert "只判断" in SEMANTIC_RELATION_JUDGE_SYSTEM and "不得" in SEMANTIC_RELATION_JUDGE_SYSTEM
