import json


def test_obvious_policy_skips_llm():
    from scripts.l1_collect.policy_gate import gate_one
    called = []
    r = gate_one(ref="r1",
                 url="https://ndrc.gov.cn/xxgk/zcfb/202501/d.html",
                 title="关于推进充电基础设施建设的指导意见",
                 body_head="根据国务院部署,现就有关事项通知如下:",
                 llm_fn=lambda s, u, **k: called.append(1) or "{}")
    assert r.label == "policy" and r.used_llm is False and r.action == "pass"
    assert not called


def test_blacklist_fast_reject():
    from scripts.l1_collect.policy_gate import gate_one
    r = gate_one(ref="r2", url="https://in-en.com/a.html",
                 title="充电桩市场快速增长", body_head="据记者了解...",
                 llm_fn=lambda s, u, **k: "{}")
    assert r.action == "reject" and r.used_llm is False


def test_borderline_calls_llm():
    from scripts.l1_collect.policy_gate import gate_one
    called = []
    def llm(s, u, max_tokens=512):
        called.append(1)
        return json.dumps({"label": "non_policy_index", "confidence": 0.85,
                          "evidence": "仅列表链接"})
    r = gate_one(ref="r3", url="https://fgw.gd.gov.cn/index.html",
                 title="政策文件目录", body_head="2025-01 政策A\n2024-12 政策B",
                 llm_fn=llm)
    assert called and r.used_llm is True and r.action == "reject"


def test_low_conf_to_review_queue():
    from scripts.l1_collect.policy_gate import gate_one
    # 灰区输入(标题/正文均无政策信号词)→ 必走 LLM;LLM 低置信 → review_queue
    r = gate_one(ref="r4", url="https://fgw.hunan.gov.cn/x.html",
                 title="某栏目页", body_head="详见下方内容列表",
                 llm_fn=lambda s, u, **k: json.dumps(
                     {"label": "non_policy_news", "confidence": 0.55, "evidence": "x"}))
    assert r.action == "review_queue"
