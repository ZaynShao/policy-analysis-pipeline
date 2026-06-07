import textwrap
from pathlib import Path


def _write_policy(d: Path, name: str, title: str):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(textwrap.dedent(f"""\
        ---
        id: P_TEST_1
        title: {title}
        date: '2026-01-01'
        region:
          level: 省
          code: '320000'
          name: 江苏省
        provenance:
          url: https://swt.jiangsu.gov.cn/x.html
        type: policy
        ---
        ## 政策原文
        正文。
        """), encoding="utf-8")


def test_route_files_transforms_and_moves(tmp_path, monkeypatch):
    from scripts._oneshot import route_interpretations as ri
    pol = tmp_path / "policies"; com = tmp_path / "commentaries"
    com.mkdir(parents=True)
    _write_policy(pol, "解读.md", "《某细则》政策解读")
    monkeypatch.setattr(ri, "POLICIES", pol)
    monkeypatch.setattr(ri, "COMMENTARIES", com)
    moved = ri.route_files([pol / "解读.md"], index=[], dry=False)
    assert moved == 1
    assert not (pol / "解读.md").exists()           # 原文件移走
    out = (com / "解读.md").read_text(encoding="utf-8")
    assert "type: 政策评论" in out
    assert "commentary_kind: official" in out
    assert "## 政策原文" in out                      # body 保留


def test_route_files_dry_no_write(tmp_path, monkeypatch):
    from scripts._oneshot import route_interpretations as ri
    pol = tmp_path / "policies"; com = tmp_path / "commentaries"; com.mkdir(parents=True)
    _write_policy(pol, "x.md", "《Y办法》问答")
    monkeypatch.setattr(ri, "POLICIES", pol); monkeypatch.setattr(ri, "COMMENTARIES", com)
    n = ri.route_files([pol / "x.md"], index=[], dry=True)
    assert n == 1
    assert (pol / "x.md").exists()                   # DRY 不动
    assert not (com / "x.md").exists()
