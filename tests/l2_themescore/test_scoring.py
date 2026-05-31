from scripts.l2_themescore.models import Scores
from scripts.l2_themescore.scoring import importance, action_class, gate_passed_deep, value_tags

def test_importance_formula():
    assert importance(Scores(5,4,4,0,0,0)) == 4
    assert importance(Scores(3,3,3,0,0,0)) == 3
    assert importance(Scores(0,0,0,0,0,0)) == 0

def test_action_class_matrix_and_modifier():
    assert action_class(Scores(5,5,5,5,5,3)) == "A"
    assert action_class(Scores(3,3,3,2,2,5)) == "C"
    assert action_class(Scores(3,3,3,5,2,1)) == "C"

def test_gate():
    assert gate_passed_deep(importance_val=3, region_level="市") is True
    assert gate_passed_deep(importance_val=2, region_level="国家") is True
    assert gate_passed_deep(importance_val=2, region_level="省") is True
    assert gate_passed_deep(importance_val=2, region_level="市") is False

def test_value_tags_subset():
    tags = value_tags(importance_val=4, themes=["power_market"])
    assert set(tags) <= {"合规","机会","壁垒","趋势"}
