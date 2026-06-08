"""PostgreSQL 写入。SQL 构造为纯函数（重测）；执行为薄 psycopg2 封装。

注意：列名用 Prisma 默认 camelCase（被 quote）。pipeline 只写 SQL，列名对齐
heng-guan Prisma schema（spec §5.1）。任一侧改动需同步 spec §5。
"""
from __future__ import annotations


def build_policy_upsert(row: dict) -> tuple[str, dict]:
    """INSERT ... ON CONFLICT (pipelinePid) DO UPDATE。
    importance 仅在 importanceOverride IS NULL 时更新（spec §5.4 核心约束）。"""
    sql = '''
    INSERT INTO "Policy"
      ("id", "pipelinePid", "pipelineVersion", "importance",
       "pipelineScores", "pipelineThemes", "pipelineImpact", "syncedAt",
       "title", "issuer", "issueDate", "content", "source",
       "docNumber", "sourceUrl", "region", "level", "updatedAt")
    VALUES
      (gen_random_uuid()::text, %(pipeline_pid)s, %(pipeline_version)s,
       %(importance)s::"PolicyImportance",
       %(pipeline_scores)s::jsonb, %(pipeline_themes)s::jsonb,
       %(pipeline_impact)s, now(),
       %(title)s, %(issuer)s, %(issue_date)s, %(content)s, %(source)s::"PolicySource",
       %(doc_number)s, %(source_url)s, %(region)s, %(level)s, now())
    ON CONFLICT ("pipelinePid") DO UPDATE SET
      "pipelineVersion" = EXCLUDED."pipelineVersion",
      "pipelineScores"  = EXCLUDED."pipelineScores",
      "pipelineThemes"  = EXCLUDED."pipelineThemes",
      "pipelineImpact"  = EXCLUDED."pipelineImpact",
      "syncedAt"        = now(),
      "title"           = EXCLUDED."title",
      "issuer"          = EXCLUDED."issuer",
      "issueDate"       = EXCLUDED."issueDate",
      "content"         = EXCLUDED."content",
      "source"          = EXCLUDED."source",
      "docNumber"       = EXCLUDED."docNumber",
      "sourceUrl"       = EXCLUDED."sourceUrl",
      "region"          = EXCLUDED."region",
      "level"           = EXCLUDED."level",
      "updatedAt"       = now(),
      "importance"      = CASE
        WHEN "Policy"."importanceOverride" IS NULL THEN EXCLUDED."importance"
        ELSE "Policy"."importance"
      END
    '''
    params = {
        "pipeline_pid": row["pipeline_pid"],
        "pipeline_version": row["pipeline_version"],
        "importance": row["importance"],
        "pipeline_scores": row["pipeline_scores"],
        "pipeline_themes": row["pipeline_themes"],
        "pipeline_impact": row["pipeline_impact"],
        "title": row["title"],
        "issuer": row["issuer"],
        "issue_date": row["issue_date"],
        "content": row["content"],
        "source": row["source"],
        "doc_number": row["doc_number"],
        "source_url": row["source_url"],
        "region": row["region"],
        "level": row["level"],
    }
    return sql, params


def build_relation_upsert(row: dict, from_cuid: str, to_cuid: str) -> tuple[str, dict]:
    sql = '''
    INSERT INTO "PolicySemanticRelation"
      ("id", "fromPolicyId", "toPolicyId", "relationType",
       "confidence", "evidence", "pipelineVersion", "createdAt")
    VALUES
      (gen_random_uuid()::text, %(from_cuid)s, %(to_cuid)s, %(relation_type)s,
       %(confidence)s, %(evidence)s, %(pipeline_version)s, now())
    ON CONFLICT ("fromPolicyId", "toPolicyId", "relationType") DO UPDATE SET
      "confidence" = EXCLUDED."confidence",
      "evidence"   = EXCLUDED."evidence",
      "pipelineVersion" = EXCLUDED."pipelineVersion"
    '''
    params = {
        "from_cuid": from_cuid,
        "to_cuid": to_cuid,
        "relation_type": row["relation_type"],
        "confidence": row["confidence"],
        "evidence": row.get("evidence"),
        "pipeline_version": row["pipeline_version"],
    }
    return sql, params


def resolve_cuid(conn, pipeline_pid: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute('SELECT "id" FROM "Policy" WHERE "pipelinePid" = %s', (pipeline_pid,))
        r = cur.fetchone()
        return r[0] if r else None


def execute(conn, sql: str, params) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


def execute_with_savepoint(conn, sql, params, name="sp") -> None:
    with conn.cursor() as cur:
        cur.execute(f"SAVEPOINT {name}")
        try:
            cur.execute(sql, params)
            cur.execute(f"RELEASE SAVEPOINT {name}")
        except Exception:
            cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise


def build_notification_insert(*, level: str, title: str, body, source: str, target_user_id=None):
    """插入一条 Notification 的 SQL+params。
    id 自带(Prisma cuid 非 DB 默认→gen_random_uuid);createdAt 走 DB 默认 now();readAt 默认 NULL。
    target_user_id=None → targetUserId 列为 NULL（广播，按角色可见）；非 None → 仅该平台账号可见。
    """
    sql = (
        'INSERT INTO "Notification" ("id","level","title","body","source","targetUserId") '
        'VALUES (gen_random_uuid()::text, %(level)s::"NotificationLevel", %(title)s, %(body)s, %(source)s, %(target_user_id)s)'
    )
    return sql, {"level": level, "title": title, "body": body, "source": source,
                 "target_user_id": target_user_id}
