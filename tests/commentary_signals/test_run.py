import json
from pathlib import Path

from scripts.commentary_signals.run import run_dryrun


def test_dryrun_writes_signals_review_queue_summary_and_html(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    com = vault / "0_raw" / "commentaries"
    reg = vault / "_meta"
    com.mkdir(parents=True)
    reg.mkdir(parents=True)
    (reg / "themes_registry.yaml").write_text(
        "themes:\n"
        "  - id: power_market\n"
        "    zh: 电力市场\n"
        "    aliases: [电力市场, 市场化, 电价]\n",
        encoding="utf-8",
    )
    (com / "评论.md").write_text(
        "---\n"
        "title: 电价市场化风险\n"
        "related_policy: [P_2025_NDRC_136]\n"
        "---\n"
        "短期收益不确定性上升。",
        encoding="utf-8",
    )

    result = run_dryrun(vault, state)

    assert result["summary"]["emitted_signals"] == 1
    assert result["summary"]["review_queue"] == 0
    assert (state / "signals.jsonl").exists()
    assert (state / "review_queue.jsonl").exists()
    assert (state / "summary.json").exists()
    assert (state / "reports" / "commentary_signals_dryrun.html").exists()
    row = json.loads((state / "signals.jsonl").read_text(encoding="utf-8").strip())
    assert row["signal_role"] == "risk"
    html = (state / "reports" / "commentary_signals_dryrun.html").read_text(encoding="utf-8")
    assert "评论校准信号 dry-run" in html
    assert "内部校准" in html


def test_dryrun_queues_linked_commentary_without_theme_hit(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    com = vault / "0_raw" / "commentaries"
    reg = vault / "_meta"
    com.mkdir(parents=True)
    reg.mkdir(parents=True)
    (reg / "themes_registry.yaml").write_text("themes: []\n", encoding="utf-8")
    (com / "评论.md").write_text(
        "---\n"
        "title: 政策解读\n"
        "related_policy: [P_2025_NDRC_136]\n"
        "---\n"
        "这是解读。",
        encoding="utf-8",
    )

    result = run_dryrun(vault, state)

    assert result["summary"]["emitted_signals"] == 1
    assert result["summary"]["review_queue"] == 1
    row = json.loads((state / "review_queue.jsonl").read_text(encoding="utf-8").strip())
    assert row["reason"] == "linked_commentary_without_theme_hit"


def test_dryrun_queues_unreadable_linked_commentary_and_html_is_text(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    com = vault / "0_raw" / "commentaries"
    reg = vault / "_meta"
    com.mkdir(parents=True)
    reg.mkdir(parents=True)
    (reg / "themes_registry.yaml").write_text(
        "themes:\n"
        "  - id: v2g\n"
        "    zh: V2G(车网互动)\n"
        "    aliases: [V2G, 车网互动]\n",
        encoding="utf-8",
    )
    (com / "评论.md").write_text(
        "---\n"
        "title: V2G政策解读\n"
        "related_policy: [P_2024_NDRC_718]\n"
        "---\n"
        "%PDF-1.7 \x00\x01\x02 乱码正文 V2G",
        encoding="utf-8",
    )

    result = run_dryrun(vault, state)

    assert result["summary"]["emitted_signals"] == 1
    assert result["summary"]["review_queue"] == 1
    row = json.loads((state / "review_queue.jsonl").read_text(encoding="utf-8").strip())
    assert row["reason"] == "linked_commentary_unreadable_body"
    html = (state / "reports" / "commentary_signals_dryrun.html").read_text(encoding="utf-8")
    assert "\x00" not in html
    assert "正文不可读" in html


def test_dryrun_does_not_modify_commentary(tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    com = vault / "0_raw" / "commentaries"
    reg = vault / "_meta"
    com.mkdir(parents=True)
    reg.mkdir(parents=True)
    (reg / "themes_registry.yaml").write_text("themes: []\n", encoding="utf-8")
    path = com / "评论.md"
    path.write_text("---\ntitle: 无关联\n---\n正文", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    run_dryrun(vault, state)

    assert path.read_text(encoding="utf-8") == before
