import json, textwrap
from scripts.l1_audit.run_audit import run_dry_run

def _write(d, name, fm, body="## 政策原文\n正文。"):
    (d / name).write_text(f"---\n{textwrap.dedent(fm).strip()}\n---\n\n{body}\n", encoding="utf-8")

def test_end_to_end_dry_run(tmp_path):
    pol = tmp_path / "0_raw" / "policies"; pol.mkdir(parents=True)
    _write(pol, "good.md", """
        id: P_2025_NDRC_357_a
        title: 关于加快推进虚拟电厂发展的指导意见
        issuer: 国家发展和改革委员会
        provenance: {url: 'https://www.ndrc.gov.cn/a/x.html'}
        date: '2025-03-01'
    """)
    _write(pol, "news.md", """
        id: P_2025_X_news
        title: 某政策解读_市县
        issuer: 搜狐
        provenance: {url: 'https://www.sohu.com/a.html'}
        date: '2025-04-01'
    """)
    out_dir = tmp_path / "state" / "source_ready"
    def fake_llm(system, user):
        return '{"label":"news_release","confidence":0.97,"evidence":"媒体"}'
    run_dry_run(policies_dir=str(pol), out_dir=str(out_dir), llm_fn=fake_llm)
    lines = (out_dir / "proposed_changes.jsonl").read_text(encoding="utf-8").strip().splitlines()
    pids = {json.loads(l)["pid"] for l in lines}
    assert "P_2025_X_news" in pids        # 新闻稿被 flag
    assert "P_2025_NDRC_357_a" not in pids # 真政策不被 flag
