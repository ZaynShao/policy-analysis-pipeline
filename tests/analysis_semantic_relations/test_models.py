from scripts.analysis_semantic_relations.models import (
    SemanticCandidate, canonical_pair, candidate_id, DIRECTED, SYMMETRIC,
)


def test_canonical_pair_symmetric_sorts_by_pid():
    assert canonical_pair("P_B", "P_A", "aligns_with") == ("P_A", "P_B")
    # 有向关系保留原方向
    assert canonical_pair("P_B", "P_A", "derives_from") == ("P_B", "P_A")


def test_candidate_id_stable_and_direction_aware():
    a = candidate_id("P_A", "P_B", "derives_from")
    assert a == candidate_id("P_A", "P_B", "derives_from")
    assert a != candidate_id("P_B", "P_A", "derives_from")  # 有向:换向不同 id
    # 对称:两向同 id(因 canonical_pair 已排序)
    assert candidate_id(*canonical_pair("P_B", "P_A", "aligns_with"), "aligns_with") == \
           candidate_id(*canonical_pair("P_A", "P_B", "aligns_with"), "aligns_with")


def test_relation_sets():
    assert "aligns_with" in SYMMETRIC
    assert {"derives_from", "extends", "iterates"} <= DIRECTED
