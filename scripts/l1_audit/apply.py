"""Phase-2 apply(2a):archive + dedup。纯文件操作(move + frontmatter 编辑);
git 跟踪由调用方在 vault 仓 commit 时做。移动不删除,可逆。"""
from __future__ import annotations
import re
from pathlib import Path
import yaml
from scripts.l1_audit.corpus import load_policies

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def _pid_to_path(policies_dir: str) -> dict:
    return {r.pid: r.path for r in load_policies(policies_dir) if r.pid}


def archive_policy(policies_dir: str, pid: str, archive_dir: str) -> str:
    src = Path(_pid_to_path(policies_dir)[pid])
    Path(archive_dir).mkdir(parents=True, exist_ok=True)
    dst = Path(archive_dir) / src.name
    src.rename(dst)
    return str(dst)


def move_duplicate(policies_dir: str, pid: str, keep_pid: str,
                   duplicates_dir: str, dedup_at: str) -> str:
    src = Path(_pid_to_path(policies_dir)[pid])
    text = src.read_text(encoding="utf-8")
    m = _FM_RE.search(text)
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2) or ""
    fm["_duplicate_of"] = keep_pid
    fm["dedup_at"] = dedup_at
    fm["dedup_rule"] = "three_dim_url_offnum_title"
    Path(duplicates_dir).mkdir(parents=True, exist_ok=True)
    dst = Path(duplicates_dir) / src.name
    new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
    dst.write_text(f"---\n{new_fm}---\n\n{body.lstrip(chr(10))}\n", encoding="utf-8")
    src.unlink()
    return str(dst)
