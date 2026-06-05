from scripts.analysis_semantic_relations.program_gate import check_candidate_row, partition_by_decision, WHITELIST


def test_schema_and_whitelist():
    ok = {"from": "A", "to": "B", "rel": "iterates", "evidence": {}, "candidate_basis": ["x"]}
    assert check_candidate_row(ok) == []
    assert check_candidate_row({**ok, "rel": "conflicts_with"})  # 非白名单→报错
    assert check_candidate_row({k: v for k, v in ok.items() if k != "evidence"})  # 缺字段


def test_partition_excludes_nonaccept():
    cands = [{"candidate_id": "c1", "from": "A", "to": "B", "rel": "iterates"},
             {"candidate_id": "c2", "from": "C", "to": "D", "rel": "aligns_with", "symmetric": True}]
    judg = {"c1": "accept", "c2": "manual_review"}
    accepted, manual = partition_by_decision(cands, judg)
    assert [c["candidate_id"] for c in accepted] == ["c1"]
    assert [c["candidate_id"] for c in manual] == ["c2"]


def test_direction_conflict_to_manual():
    cands = [{"candidate_id": "c1", "from": "A", "to": "B", "rel": "derives_from"},
             {"candidate_id": "c2", "from": "B", "to": "A", "rel": "iterates"}]
    judg = {"c1": "accept", "c2": "accept"}
    accepted, manual = partition_by_decision(cands, judg)
    assert accepted == []                      # 互斥有向 → 都不进 accepted
    assert {c["candidate_id"] for c in manual} == {"c1", "c2"}
