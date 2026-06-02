from scripts.l2_themescore.models import BusinessViewDraft, QueueRecord, Scores
from scripts.l2_themescore.report import render


def test_render_writes_html(tmp_path):
    draft = BusinessViewDraft(
        pid="P1",
        themes=["power_market"],
        primary_theme="power_market",
        scores=Scores(5, 4, 4, 4, 4, 5),
        importance=4,
        gate_passed_deep=True,
    )
    queue = [QueueRecord(pid="P2", stage="judge_reject", reason="漏挂")]
    out = tmp_path / "dryrun.html"

    render([draft], queue, [], None, str(out))

    assert "②-B 归属挂载" in out.read_text(encoding="utf-8")
