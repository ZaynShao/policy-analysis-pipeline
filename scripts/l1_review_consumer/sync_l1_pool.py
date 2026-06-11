"""forward 传输:pool.jsonl → 衡观 PG 表 L1ReviewQueue。

新脚本,复用 run_sync 的 psycopg2 直写 + ON CONFLICT,但**不改** service-deploy 的
run_sync/sync_tick。纯映射逻辑可单测;真 PG 写入在 main()(需 DATABASE_URL,由
「知识库服务上云」session 在服务器上跑)。

ON CONFLICT 只在 verdict IS NULL 时更新 → 已被人判过的行不被新一轮 sync 覆盖。
"""
import hashlib
import os
from scripts.l1_collect.review_pool import load, POOL

TABLE = "L1ReviewQueue"

# pool 行 → PG 列(顺序固定,build_upsert 依赖)
_COLS = ("dedupeKey", "pipelineKind", "pipelineRef", "reason",
         "suggestedAction", "confidence", "evidence", "channel", "runLabel",
         "verdict")


def pool_row_to_pg(r: dict) -> dict:
    dedupe_key = f'{r["kind"]}::{r["ref"]}'
    return {
        "id": "l1_" + hashlib.sha1(dedupe_key.encode("utf-8")).hexdigest()[:24],
        "dedupeKey": dedupe_key,
        "pipelineKind": r["kind"],
        "pipelineRef": r["ref"],
        "reason": r.get("reason"),
        "suggestedAction": r.get("suggested_action"),
        "confidence": r.get("confidence"),
        "evidence": r.get("evidence"),
        "channel": r.get("channel"),
        "runLabel": r.get("run_label"),
        "verdict": None,
    }


def build_upsert(row: dict):
    cols = list(row.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    colnames = ", ".join(f'"{c}"' for c in cols)
    # 已判行不动:DO UPDATE SET 排除 verdict + WHERE verdict IS NULL
    updates = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "verdict")
    sql = (
        f'INSERT INTO "{TABLE}" ({colnames}, "createdAt") '
        f'VALUES ({placeholders}, now()) '
        f'ON CONFLICT ("dedupeKey") DO UPDATE SET {updates} '
        f'WHERE "{TABLE}"."verdict" IS NULL'
    )
    return sql, [row[c] for c in cols]


def main(pool_path=POOL):
    import psycopg2
    rows = [pool_row_to_pg(r) for r in load(pool_path)]
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        ok = 0
        for row in rows:
            sql, params = build_upsert(row)
            cur.execute("SAVEPOINT s")
            try:
                cur.execute(sql, params)
                cur.execute("RELEASE SAVEPOINT s")
                ok += 1
            except Exception as e:  # 单行坏不阻断批次
                cur.execute("ROLLBACK TO SAVEPOINT s")
                print(f"skip {row['dedupeKey']}: {e}")
        conn.commit()
        print(f"forward synced {ok}/{len(rows)} rows → PG {TABLE}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
