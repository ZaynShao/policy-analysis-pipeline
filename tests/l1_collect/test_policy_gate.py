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


def test_heuristic_commentary_before_gov_fastpass():
    """《X办法》政策解读:含'办法'政策信号+gov域,但应先判 commentary(堵旧洞)。"""
    from scripts.l1_collect.policy_gate import _heuristic
    v = _heuristic("https://fgw.sc.gov.cn/zcjd/x.html",
                   "《四川省绿电直连实施细则》政策解读", "")
    assert v == "commentary"


def test_gate_one_commentary_action():
    from scripts.l1_collect.policy_gate import gate_one
    gr = gate_one("p1", "https://x.gov.cn/zcjd/a.html",
                  "《某办法》答记者问", "记者问……", llm_fn=None)
    assert gr.label == "commentary"
    assert gr.action == "commentary"


def test_gate_one_llm_commentary_label_maps_to_action():
    # 灰区URL(gov域名但标题无政策信号词)+LLM返回commentary → action应为commentary
    import json
    from scripts.l1_collect.policy_gate import gate_one
    def fake(system, user):
        return json.dumps({"label": "commentary", "confidence": 0.9, "evidence": "解读口径"})
    gr = gate_one("p2", "https://fgw.gd.gov.cn/zcjd/a.html", "某栏目介绍", "", llm_fn=fake)
    assert gr.action == "commentary"


def test_procurement_announcement_not_policy_no_llm():
    """采购中标公告:gov 域 + 含'公告',旧逻辑 heuristic 直通 policy;
    现应确定性 reject(非政策标题黑名单),不浪费 LLM。"""
    from scripts.l1_collect.policy_gate import gate_one
    called = []
    r = gate_one(ref="proc",
                 url="https://amr.hainan.gov.cn/x.html",
                 title="海南省市场监督管理局采购项目中标公告",
                 body_head="一、项目名称……二、中标供应商……",
                 llm_fn=lambda s, u, **k: called.append(1) or "{}")
    assert r.action == "reject"
    assert not called


def test_party_activity_not_autopassed_by_body_signal():
    """党建活动:正文含'根据'(旧 body 信号直通);现不得 auto-pass 为 policy。"""
    from scripts.l1_collect.policy_gate import gate_one
    r = gate_one(ref="party",
                 url="https://scjgj.nc.gov.cn/x.html",
                 title="南昌市市场监管局开展大学习大讨论大提升活动",
                 body_head="根据上级部署,我局组织开展……",
                 llm_fn=None)
    assert r.action != "pass"


def test_gov_body_signal_alone_no_heuristic_autopass():
    """gov 域 + 标题无政策信号词 + 正文含'现将':不得 heuristic 直通,应交 LLM 裁决。"""
    import json
    from scripts.l1_collect.policy_gate import gate_one
    called = []
    def llm(s, u, **k):
        called.append(1)
        return json.dumps({"label": "non_policy_news", "confidence": 0.9, "evidence": "新闻"})
    r = gate_one(ref="body",
                 url="https://samr.gov.cn/x.html",
                 title="市场监管总局发布反垄断执法年度报告",
                 body_head="为加强监管,现将有关情况通报如下:",
                 llm_fn=llm)
    assert called
    assert r.used_llm is True
