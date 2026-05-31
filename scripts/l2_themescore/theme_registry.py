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
