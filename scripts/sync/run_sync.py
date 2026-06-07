"""Sync 入口：vault 派生产物 → heng-guan PostgreSQL upsert。

只 upsert，不删除；不碰 pipelinePid IS NULL 的手动录入记录（靠 ON CONFLICT 语义）。
importance 不踩人工 override（SQL CASE 守卫，见 pg_writer）。
"""
from __future__ import annotations
import argparse
import glob
import json
import os
from pathlib import Path

import yaml

from scripts.sync.policy_mapper import map_business_view
from scripts.sync.relation_mapper import map_relation
from scripts.sync import pg_writer


def collect_policy_rows(vault: Path, pipeline_version: int) -> list[dict]:
    rows = []
    for fp in sorted(glob.glob(str(Path(vault) / "_meta" / "business_view" / "*.yaml"))):
        bv = yaml.safe_load(Path(fp).read_text(encoding="utf-8"))
        if bv and bv.get("pid"):
            rows.append(map_business_view(bv, pipeline_version))
    return rows


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


def build_summary(synced: int, skipped_override: int, relations: int, errors: list[str]) -> dict:
    return {
        "synced_count": synced,
        "skipped_override_count": skipped_override,
        "relation_count": relations,
        "errors": errors,
    }


def run(vault: Path, state_dir: Path, pipeline_version: int, database_url: str) -> dict:
    import psycopg2
    policy_rows = collect_policy_rows(vault, pipeline_version)
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
    summary = build_summary(synced, 0, rel_synced, errors)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
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
