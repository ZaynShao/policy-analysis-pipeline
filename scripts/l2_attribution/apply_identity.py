"""§C 合规就地写 raw 身份字段。yaml round-trip,审计嵌 provenance,文件名不变。"""
from __future__ import annotations
import re
from pathlib import Path
import yaml

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def apply_identity(path: str, ri, fixed_at: str) -> list:
    """按 ResolvedIdentity.fields 改 frontmatter;无字段则完全不动。返回写了哪些字段。"""
    if not ri.fields:
        return []
    src = Path(path)
    text = src.read_text(encoding="utf-8")
    m = _FM_RE.search(text)
    if not m:
        raise ValueError(f"{src} 无 frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2) or ""
    prov = fm.get("provenance") or {}
    if not isinstance(prov, dict):
        prov = {}

    written = []
    # id 特殊:先处理 aliases(旧+新)
    if "id" in ri.fields:
        new_id = ri.fields["id"].value
        old_id = fm.get("id")
        aliases = fm.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = [aliases]
        if old_id and old_id not in aliases:
            aliases.append(old_id)
        if new_id not in aliases:
            aliases.append(new_id)
        fm["aliases"] = aliases

    for name, rf in ri.fields.items():
        fm[name] = rf.value
        prov[f"{name}_fixed_at"] = fixed_at
        prov[f"{name}_fixed_method"] = rf.method
        prov[f"{name}_fixed_from"] = rf.from_val
        if rf.confidence is not None:
            prov[f"{name}_fix_confidence"] = rf.confidence
        written.append(name)

    fm["provenance"] = prov
    new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
    src.write_text(f"---\n{new_fm}---\n\n{body.lstrip(chr(10))}\n", encoding="utf-8")
    return written
