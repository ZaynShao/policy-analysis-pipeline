from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass
class ThemeRegistry:
    ids: list
    zh: dict
    aliases: dict
    alias_index: dict

    @classmethod
    def load(cls, path: str):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        themes = data.get("themes") or []
        ids, zh, aliases, alias_index = [], {}, {}, {}
        for t in themes:
            tid = t["id"]; ids.append(tid)
            zh[tid] = t.get("zh", tid)
            al = list(t.get("aliases") or [])
            aliases[tid] = al
            for a in al:
                alias_index.setdefault(a, []).append(tid)
        return cls(ids=ids, zh=zh, aliases=aliases, alias_index=alias_index)

    def is_valid(self, tid: str) -> bool:
        return tid in self.zh


def canonical_theme_id(tid: str, valid_ids) -> str:
    if not tid:
        return ""
    valid = set(valid_ids)
    if tid in valid:
        return tid
    if tid.endswith("_theme"):
        base = tid[:-6]
        if base in valid:
            return base
    return tid


def canonicalize_theme_ids(ids, valid_ids) -> list:
    out = []
    seen = set()
    for tid in ids or []:
        canon = canonical_theme_id(tid, valid_ids)
        if not canon:
            continue
        if canon not in seen:
            out.append(canon)
            seen.add(canon)
    return out
