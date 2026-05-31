"""子项 b · 词表校验(只读 lint):扫 themes_registry + entities/registry。
查:重复 id / alias 冲突(同 alias→多 id) / theme↔entity 不自洽 / 缺必填。产报告。"""
from __future__ import annotations
import sys
from pathlib import Path
from collections import defaultdict
import yaml


def _dups(ids: list[str]) -> list[str]:
    seen, dup = set(), set()
    for i in ids:
        (dup if i in seen else seen).add(i)
    return sorted(dup)


def _alias_conflicts(items: list[dict], id_key: str, alias_key: str = "aliases") -> dict:
    """同一 alias 字符串映射到 >1 个不同 id → 冲突。"""
    amap = defaultdict(set)
    for it in items:
        for a in (it.get(alias_key) or []):
            amap[a].add(it.get(id_key))
    return {a: sorted(ids) for a, ids in amap.items() if len(ids) > 1}


def check(themes_path: str, entities_path: str) -> dict:
    themes = (yaml.safe_load(Path(themes_path).read_text(encoding="utf-8")) or {}).get("themes", [])
    # entities/registry.yaml = 多文档(--- 元信息头 --- 实体列表)。取其中的 list 文档。
    docs = list(yaml.safe_load_all(Path(entities_path).read_text(encoding="utf-8")))
    entities = next((d for d in docs if isinstance(d, list)), [])
    if not entities:
        for d in docs:
            if isinstance(d, dict) and (d.get("entities") or d.get("items")):
                entities = d.get("entities") or d.get("items")
                break

    theme_ids = [t.get("id") for t in themes]
    ent_ids = [e.get("id") for e in entities]
    ent_by_id = {e.get("id"): e for e in entities}
    theme_type_ids = {e.get("id") for e in entities if "theme" in (e.get("type") or [])}

    # 实体 alias 冲突分两类:真冲突(同 alias→≥2 theme,或≥2 个全非 theme) vs 结构性(1 theme + 其 concept,可接受)
    raw_ent_conf = _alias_conflicts(entities, "id")
    ent_conf_real, ent_conf_structural = {}, {}
    for alias, ids in raw_ent_conf.items():
        types = [(i, "theme" if "theme" in (ent_by_id.get(i, {}).get("type") or []) else "other") for i in ids]
        n_theme = sum(1 for _, t in types if t == "theme")
        if n_theme >= 2 or (n_theme == 0 and len(ids) >= 2):
            ent_conf_real[alias] = ids
        else:
            ent_conf_structural[alias] = ids

    r = {
        "themes_n": len(themes), "entities_n": len(entities),
        "theme_dup_ids": _dups(theme_ids),
        "entity_dup_ids": _dups(ent_ids),
        "theme_alias_conflicts": _alias_conflicts(themes, "id"),
        "entity_alias_conflicts": ent_conf_real,
        "entity_alias_structural_ok": ent_conf_structural,
        # 自洽:每个 theme 需有同 id 的 type=theme entity
        "themes_without_entity": sorted([t.get("id") for t in themes if t.get("id") not in theme_type_ids]),
        "theme_entities_without_registry": sorted([i for i in theme_type_ids if i not in set(theme_ids)]),
        "themes_missing_fields": sorted([t.get("id") or "(no-id)" for t in themes
                                         if not t.get("id") or not t.get("zh") or not t.get("aliases")]),
        "entities_missing_fields": sorted([e.get("id") or "(no-id)" for e in entities
                                           if not e.get("id") or not e.get("canonical_name") or not e.get("type")]),
    }
    r["clean"] = not any([r["theme_dup_ids"], r["entity_dup_ids"], r["theme_alias_conflicts"],
                          r["entity_alias_conflicts"], r["themes_without_entity"],
                          r["theme_entities_without_registry"], r["themes_missing_fields"],
                          r["entities_missing_fields"]])
    return r


def write_report(r: dict, out: str) -> None:
    L = ["# 子项 b · 词表校验报告", "", f"- themes: {r['themes_n']} | entities: {r['entities_n']}",
         f"- **结论: {'✅ 自洽,无冲突' if r['clean'] else '⚠ 见下方问题'}**", ""]
    def sec(title, val):
        L.append(f"## {title}")
        if not val:
            L.append("- (无)")
        elif isinstance(val, dict):
            for k, v in val.items():
                L.append(f"- `{k}` → {v}")
        else:
            for v in val:
                L.append(f"- `{v}`")
        L.append("")
    sec("theme 重复 id", r["theme_dup_ids"])
    sec("entity 重复 id", r["entity_dup_ids"])
    sec("theme alias 冲突(同词→多id)", r["theme_alias_conflicts"])
    sec("entity alias 真冲突(同词→≥2 theme 或 ≥2 非theme)", r["entity_alias_conflicts"])
    sec("entity alias 结构性重叠(theme+其concept,可接受,仅记录)", r.get("entity_alias_structural_ok", {}))
    sec("theme 缺对应 type=theme entity(不自洽)", r["themes_without_entity"])
    sec("type=theme entity 缺 themes_registry 条目", r["theme_entities_without_registry"])
    sec("themes 缺必填(id/zh/aliases)", r["themes_missing_fields"])
    sec("entities 缺必填(id/canonical_name/type)", r["entities_missing_fields"])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", required=True)
    ap.add_argument("--entities", required=True)
    ap.add_argument("--out", default="state/source_ready/vocab_check.md")
    a = ap.parse_args()
    r = check(a.themes, a.entities)
    write_report(r, a.out)
    print(f"[vocab] clean={r['clean']} themes={r['themes_n']} entities={r['entities_n']} -> {a.out}")
    for k in ("theme_dup_ids", "entity_dup_ids", "theme_alias_conflicts", "entity_alias_conflicts",
              "themes_without_entity", "theme_entities_without_registry",
              "themes_missing_fields", "entities_missing_fields"):
        v = r[k]
        if v:
            print(f"  ⚠ {k}: {v}")


if __name__ == "__main__":
    main()
