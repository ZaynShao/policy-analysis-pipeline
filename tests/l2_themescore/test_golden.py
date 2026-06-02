from scripts.l2_themescore.golden import load_golden, score_judge

def test_load_golden(tmp_path):
    p = tmp_path/"g.jsonl"
    p.write_text(
        '{"pid":"P1","gold_themes":["power_market"],"gold_primary":"power_market","gold_scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5},"is_planted":false}\n'
        '{"pid":"P2","gold_themes":["x"],"gold_primary":"x","gold_scores":{"D1":1,"D2":1,"D3":1,"D4":1,"D5":1,"D6":1},"is_planted":true,"error_type":"低估"}\n',
        encoding="utf-8")
    recs = load_golden(str(p))
    assert len(recs) == 2 and recs[1].is_planted

def test_load_golden_accepts_frozen_v1_shape(tmp_path):
    p = tmp_path/"g.jsonl"
    p.write_text(
        '{"pid":"P1","themes":["power_market"],"primary_theme":"power_market","scores":{"D1":5,"D2":4,"D3":4,"D4":4,"D5":4,"D6":5},"is_planted":false}\n',
        encoding="utf-8")
    rec = load_golden(str(p))[0]
    assert rec.gold_themes == ["power_market"]
    assert rec.gold_primary == "power_market"
    assert rec.gold_scores["D1"] == 5

def test_score_judge_recall_precision():
    # rows: list[(pid, verdict, is_planted)]
    rows = [("P1","accept",False), ("P2","reject",True)]
    r = score_judge(rows)
    assert r["recall"] == 1.0 and r["precision"] == 1.0

def test_score_judge_misses_and_falsepos():
    # P2 planted but accepted (miss), P3 clean but rejected (false pos)
    rows = [("P1","accept",False), ("P2","accept",True), ("P3","reject",False)]
    r = score_judge(rows)
    assert r["recall"] == 0.0          # 1 planted, 0 caught
    assert r["precision"] == 0.0       # 1 rejected, 0 真错
