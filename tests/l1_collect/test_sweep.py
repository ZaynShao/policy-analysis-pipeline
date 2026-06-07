from pathlib import Path


def _pol(d, name, title):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\nid: P_X\ntitle: {title}\ntype: policy\n---\n## 政策原文\nx\n",
                          encoding="utf-8")


def test_sweep_detects_marker_titles(tmp_path, monkeypatch):
    from scripts._oneshot import sweep_existing_commentary as sw
    pol = tmp_path / "policies"
    _pol(pol, "a.md", "某省成品油管理办法")            # 真政策,不命中
    _pol(pol, "b.md", "《某办法》政策解读")             # 命中
    _pol(pol, "c.md", "国家能源局有关负责同志答记者问")   # 命中
    monkeypatch.setattr(sw, "POLICIES", pol)
    hits = sw.detect_commentary(pol)
    names = {p.name for p in hits}
    assert names == {"b.md", "c.md"}
