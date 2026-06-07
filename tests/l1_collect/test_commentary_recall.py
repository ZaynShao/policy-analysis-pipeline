def test_commentary_recall_deterministic():
    """marker 标题的 commentary golden 经 gate(llm_fn=None)应 100% recall。"""
    from scripts.l1_collect.policy_gate import gate_one, GoldenRecord
    from scripts._oneshot.calibrate_l1_gate import compute_commentary_recall

    golden = [
        GoldenRecord(pid="t1", url="https://x.gov.cn/zcjd/a.html",
                     title="《某办法》政策解读", body_head="解读",
                     gold_label="commentary", is_planted=False),
        GoldenRecord(pid="t2", url="https://x.gov.cn/b.html",
                     title="国家能源局有关负责同志答记者问", body_head="记者问",
                     gold_label="commentary", is_planted=False),
    ]

    # Direct gate_one check
    hit = 0
    tot = 0
    for r in golden:
        if r.gold_label != "commentary":
            continue
        tot += 1
        gr = gate_one(r.pid, r.url, r.title, r.body_head, llm_fn=None)
        if gr.action == "commentary":
            hit += 1
    assert tot == 2
    assert hit / tot == 1.0

    # Reusable helper check (llm_fn=None)
    recall = compute_commentary_recall(golden, llm_fn=None)
    assert recall == 1.0
