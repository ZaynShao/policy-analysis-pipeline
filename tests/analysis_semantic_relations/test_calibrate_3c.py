"""Tests for calibrate_3c_judge.py — pure scoring and row-reconstruction helpers.

No network calls, no real golden file needed.
"""
import pytest

from scripts._oneshot.calibrate_3c_judge import row_to_candidate, score_calibration


# ---------------------------------------------------------------------------
# row_to_candidate
# ---------------------------------------------------------------------------

def test_row_to_candidate_required_keys():
    row = {
        "from": "P_A",
        "to": "P_B",
        "rel": "iterates",
        "from_title": "A 标题",
        "to_title": "B 标题",
        "from_window": "A 节选",
        "to_window": "B 节选",
        "candidate_basis": ["same_theme"],
        "stratum": "real",
        "is_planted": False,
        "planted_error_type": None,
        "gold_decision": "accept",
    }
    cand = row_to_candidate(row)

    assert cand["candidate_id"] == "P_A|P_B|iterates"
    assert cand["from"] == "P_A"
    assert cand["to"] == "P_B"
    assert cand["rel"] == "iterates"
    assert cand["candidate_basis"] == ["same_theme"]

    ev = cand["evidence"]
    assert set(ev.keys()) == {"from_title", "to_title", "from_window", "to_window", "theme_context"}
    assert ev["from_title"] == "A 标题"
    assert ev["to_title"] == "B 标题"
    assert ev["from_window"] == "A 节选"
    assert ev["to_window"] == "B 节选"
    assert ev["theme_context"] == []


def test_row_to_candidate_missing_optional_fields():
    """Missing optional fields default to empty strings / empty list."""
    row = {"from": "X", "to": "Y", "rel": "derives_from"}
    cand = row_to_candidate(row)
    ev = cand["evidence"]
    assert ev["from_title"] == ""
    assert ev["to_window"] == ""
    assert ev["theme_context"] == []
    assert cand["candidate_basis"] == []


# ---------------------------------------------------------------------------
# score_calibration — planted rows
# ---------------------------------------------------------------------------

def _make_rows(specs):
    """specs: list of (is_planted, gold_decision, verdict)"""
    return [
        {"is_planted": ip, "gold_decision": gd, "verdict": v}
        for ip, gd, v in specs
    ]


def test_planted_all_caught():
    """2 planted, judge gave reject + manual_review → planted_recall == 1.0, bar_pass True."""
    rows = _make_rows([
        (True, None, "reject"),
        (True, None, "manual_review"),
    ])
    s = score_calibration(rows)
    assert s["planted_recall"] == 1.0
    assert s["n_planted"] == 2
    assert s["n_planted_caught"] == 2
    assert s["bar_pass"] is True


def test_planted_one_accepted():
    """2 planted, one accepted by judge → planted_recall == 0.5, bar_pass False."""
    rows = _make_rows([
        (True, None, "accept"),       # missed — judge wrongly accepted planted
        (True, None, "reject"),       # caught
    ])
    s = score_calibration(rows)
    assert s["planted_recall"] == 0.5
    assert s["n_planted_caught"] == 1
    assert s["bar_pass"] is False


def test_planted_recall_threshold_boundary():
    """Exactly 9/10 caught → 0.9, passes bar."""
    rows = _make_rows([(True, None, "reject")] * 9 + [(True, None, "accept")])
    s = score_calibration(rows)
    assert s["planted_recall"] == 0.9
    assert s["bar_pass"] is True


def test_planted_recall_just_below():
    """8/10 caught → 0.8, fails bar."""
    rows = _make_rows([(True, None, "reject")] * 8 + [(True, None, "accept")] * 2)
    s = score_calibration(rows)
    assert s["planted_recall"] == 0.8
    assert s["bar_pass"] is False


# ---------------------------------------------------------------------------
# score_calibration — real rows
# ---------------------------------------------------------------------------

def test_real_agreement():
    """3 real rows, 2 match gold → agreement == 2/3."""
    rows = _make_rows([
        (False, "accept", "accept"),
        (False, "reject", "reject"),
        (False, "manual_review", "reject"),  # disagrees
    ])
    s = score_calibration(rows)
    assert s["n_real"] == 3
    assert abs(s["agreement"] - 2 / 3) < 1e-4  # rounded to 4 decimal places


def test_real_accept_kept():
    """2 gold-accept real rows, judge keeps 1 → real_accept_kept == 0.5."""
    rows = _make_rows([
        (False, "accept", "accept"),
        (False, "accept", "reject"),
    ])
    s = score_calibration(rows)
    assert s["real_accept_kept"] == 0.5


def test_no_gold_accept_real_rows_defaults_to_1():
    """If no real rows have gold_decision=accept, real_accept_kept defaults to 1.0."""
    rows = _make_rows([
        (False, "reject", "reject"),
        (False, "manual_review", "manual_review"),
    ])
    s = score_calibration(rows)
    assert s["real_accept_kept"] == 1.0


# ---------------------------------------------------------------------------
# score_calibration — mixed planted + real
# ---------------------------------------------------------------------------

def test_mixed_rows():
    rows = _make_rows([
        (True, None, "reject"),        # planted caught
        (True, None, "accept"),        # planted missed
        (False, "accept", "accept"),   # real agree
        (False, "reject", "accept"),   # real disagree
    ])
    s = score_calibration(rows)
    assert s["n_planted"] == 2
    assert s["n_real"] == 2
    assert s["n_planted_caught"] == 1
    assert s["planted_recall"] == 0.5
    assert s["bar_pass"] is False
    assert abs(s["agreement"] - 0.5) < 1e-6


def test_no_planted_rows():
    """No planted rows → planted_recall == 0.0, bar_pass False."""
    rows = _make_rows([(False, "accept", "accept")])
    s = score_calibration(rows)
    assert s["planted_recall"] == 0.0
    assert s["n_planted"] == 0
    assert s["bar_pass"] is False


def test_no_real_rows():
    """No real rows → agreement defaults to 1.0."""
    rows = _make_rows([(True, None, "reject")])
    s = score_calibration(rows)
    assert s["n_real"] == 0
    assert s["agreement"] == 1.0
