import json
from pathlib import Path
from scripts.analysis_semantic_relations.run import run_preview
from scripts.analysis_semantic_relations.loaders import PolicyView


class FakeClient:
    model = "fake"
    def complete(self, system, user, max_tokens=1024):
        return '{"decision":"accept","confidence":0.9,"reason":"ok"}'


def _views():
    return {"A": PolicyView("A", "甲", "省", "广东", "发改委", 2021, ["power_market"], "power_market", 3),
            "B": PolicyView("B", "乙", "省", "江苏", "发改委", 2021, ["power_market"], "power_market", 3)}


def test_run_preview_writes_outputs_no_vault(tmp_path, monkeypatch):
    import scripts.analysis_semantic_relations.run as runmod
    monkeypatch.setattr(runmod, "load_policy_views", lambda vault=None: _views())
    monkeypatch.setattr(runmod, "load_hpr_basis_pairs", lambda p: set())
    state = tmp_path / "sem"
    res = run_preview(vault=tmp_path / "vault", state=state, hpr_path=tmp_path / "none.jsonl",
                      judge_client=FakeClient())
    summ = json.loads((state / "semantic_relation_summary.json").read_text())
    assert summ["candidate_count"] >= 1 and summ["recommendation"] == "preview_only_no_apply"
    assert (state / "accepted_semantic_relations.jsonl").exists()
    assert not (tmp_path / "vault").exists()    # 绝不建/写 vault
