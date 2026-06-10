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
    from scripts.l1_collect import route_interpretations as ri
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
    from scripts.l1_collect import route_interpretations as ri
    pol = tmp_path / "policies"; com = tmp_path / "commentaries"; com.mkdir(parents=True)
    _write_policy(pol, "x.md", "《Y办法》问答")
    monkeypatch.setattr(ri, "POLICIES", pol); monkeypatch.setattr(ri, "COMMENTARIES", com)
    n = ri.route_files([pol / "x.md"], index=[], dry=True)
    assert n == 1
    assert (pol / "x.md").exists()                   # DRY 不动
    assert not (com / "x.md").exists()


def test_route_files_and_index_respect_vault_root(tmp_path, monkeypatch):
    """C1: build_title_index/route_files 用 vault_root 参数,不触碰 Path.home() 真路径。"""
    from scripts.l1_collect import route_interpretations as ri

    # 伪 vault_root,结构对齐真 vault
    vault = tmp_path / "vault"
    pol = vault / "0_raw" / "policies"
    com = vault / "0_raw" / "commentaries"
    pol.mkdir(parents=True)
    com.mkdir(parents=True)

    # policies/ 里放一篇普通政策(供 build_title_index 建索引)
    _write_policy(pol, "policy_a.md", "电力市场化改革若干意见")

    # policies/ 里放一篇解读(供 route_files 转移)
    staged = tmp_path / "staged"
    staged.mkdir()
    _write_policy(staged, "interp.md", "《电力市场化改革若干意见》政策解读")
    src_file = staged / "interp.md"

    # 保险: 让 Path.home() 指向不存在目录,证明两函数不去触碰它
    fake_home = tmp_path / "FAKE_HOME"
    monkeypatch.setattr(ri.Path, "home", staticmethod(lambda: fake_home))

    # ① build_title_index 从 vault_root 的 policies 建索引(空 skip,应扫到 policy_a)
    idx = ri.build_title_index(skip_paths=set(), vault_root=vault)
    assert len(idx) == 1, f"应从 vault_root/policies 建到 1 条索引,实得 {len(idx)}"
    assert "电力市场化改革若干意见" in idx[0][2]

    # ② route_files 落到 vault_root/commentaries/,staged 原文件被移走
    n = ri.route_files([src_file], index=idx, dry=False, vault_root=vault)
    assert n == 1
    assert not src_file.exists(), "staged 原文件应被移走"
    assert (com / "interp.md").exists(), "转移后文件应出现在 vault_root/0_raw/commentaries/"

    # ③ FAKE_HOME 下什么都没有写入
    assert not fake_home.exists(), "不应在 Path.home() 下写入任何内容"
