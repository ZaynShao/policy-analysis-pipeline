"""Sync 入口：vault 派生产物 → heng-guan PostgreSQL upsert。

只 upsert，不删除；不碰 pipelinePid IS NULL 的手动录入记录（靠 ON CONFLICT 语义）。
importance 不踩人工 override（SQL CASE 守卫，见 pg_writer）。
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
from pathlib import Path

import yaml

from scripts.l1_audit.corpus import load_policies
from scripts.sync.policy_mapper import map_business_view, map_policy_row
from scripts.sync.relation_mapper import map_relation
from scripts.sync import pg_writer

_FM = re.compile(r"^---\n.*?\n---\n?(.*)$", re.S)


def _read_full_body(path):
    t = Path(path).read_text(encoding="utf-8")
    m = _FM.match(t)
    return (m.group(1).lstrip("\n") if m else t)


def _norm_region(v):
    if not v:
        return None
    if isinstance(v, list):
        return "、".join(str(x) for x in v) or None
    return str(v)


def collect_policy_rows(vault: Path, pipeline_version: int) -> tuple[list[dict], list[dict]]:
    rows, skipped = [], []
    recs = {r.pid: r for r in load_policies(f"{vault}/0_raw/policies")}
    for fp in sorted(glob.glob(str(Path(vault) / "_meta" / "business_view" / "*.yaml"))):
        bv = yaml.safe_load(Path(fp).read_text(encoding="utf-8"))
        if not (bv and bv.get("pid")):
            continue
        pid = bv["pid"]
        rec = recs.get(pid)
        if rec is None:
            skipped.append({"pid": pid, "reason": "raw not found"})
            continue
        issuer_list = rec.issuer_canonical or rec.issuer or []
        core = {
            "title": rec.title,
            "issuer": "、".join(issuer_list),
            "date": str(rec.date or "").strip(),
            "content": _read_full_body(rec.path),
            "doc_number": rec.official_number or None,
            "source_url": rec.url or None,
            "region": _norm_region(rec.raw_fm.get("region")),
        }
        try:
            rows.append(map_policy_row(bv, core, pipeline_version))
        except ValueError as e:
            skipped.append({"pid": pid, "reason": str(e)})
    return rows, skipped


def collect_relation_rows(vault: Path, pipeline_version: int) -> list[dict]:
    rows = []
    rel_dir = Path(vault) / "1_extracted" / "relations"
    for fp in sorted(glob.glob(str(rel_dir / "*.jsonl"))):
        for line in Path(fp).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            norm = {
                "from_pid": rec.get("from"),
                "to_pid": rec.get("to"),
                "relation_type": rec.get("rel"),
                "confidence": rec.get("confidence"),
                "evidence": rec.get("evidence"),
            }
            if norm["from_pid"] and norm["to_pid"] and norm["relation_type"]:
                try:
                    rows.append(map_relation(norm, pipeline_version))
                except ValueError:
                    continue  # 未知关系类型跳过（不污染 DB）
    return rows


def build_summary(synced: int, skipped_override: int, relations: int, errors: list[str],
                  skipped_invalid: int = 0) -> dict:
    return {
        "synced_count": synced,
        "skipped_override_count": skipped_override,
        "relation_count": relations,
        "errors": errors,
        "skipped_invalid_count": skipped_invalid,
    }


def run(vault: Path, state_dir: Path, pipeline_version: int, database_url: str) -> dict:
    import psycopg2
    policy_rows, skipped_rows = collect_policy_rows(vault, pipeline_version)
    relation_rows = collect_relation_rows(vault, pipeline_version)
    errors: list[str] = []
    synced = 0
    conn = psycopg2.connect(database_url)
    try:
        for row in policy_rows:
            try:
                sql, params = pg_writer.build_policy_upsert(row)
                pg_writer.execute_with_savepoint(conn, sql, params)
                synced += 1
            except Exception as e:  # 单篇失败不崩整批
                errors.append(f"policy {row.get('pipeline_pid')}: {e}")
        rel_synced = 0
        for row in relation_rows:
            from_cuid = pg_writer.resolve_cuid(conn, row["from_pid"])
            to_cuid = pg_writer.resolve_cuid(conn, row["to_pid"])
            if not from_cuid or not to_cuid:
                continue  # 关系两端必须已存在为 Policy
            try:
                sql, params = pg_writer.build_relation_upsert(row, from_cuid, to_cuid)
                pg_writer.execute_with_savepoint(conn, sql, params)
                rel_synced += 1
            except Exception as e:
                errors.append(f"relation {row['from_pid']}->{row['to_pid']}: {e}")
        conn.commit()
    finally:
        conn.close()
    summary = build_summary(synced, 0, rel_synced, errors,
                            skipped_invalid=len(skipped_rows))
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "sync_skipped.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in skipped_rows),
        encoding="utf-8")
    (state_dir / "last_sync_run.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--pipeline-version", type=int, default=1)
    args = ap.parse_args(argv)
    database_url = os.environ["DATABASE_URL"]
    summary = run(Path(args.vault), Path(args.state_dir), args.pipeline_version, database_url)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
