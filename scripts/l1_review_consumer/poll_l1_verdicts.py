"""reverse:衡观 PG 的人审 verdict → pipeline。

- 读 PG L1ReviewQueue 已判未回灌行 → 包标准信封 → append 到 verdicts.jsonl
- 继承语义②:判完从 pool 删行(池无"已解决"态,不删则计数单调偏高)
- 幂等:verdicts.jsonl 按 idem_key 去重;PG 行置 syncedBack=true

重核(fetch_fail 重抓)/ review GC 由 applier(L1)负责,见 applier handoff。
纯逻辑函数(remove_from_pool / persist_envelope)可单测;真 PG 读在 main()。
"""
import json
from pathlib import Path

from scripts.l1_collect.review_pool import load as load_pool, POOL
from scripts.l1_review_consumer.envelope import wrap_verdict

VERDICTS_SINK = Path(POOL).parent / "verdicts.jsonl"


def remove_from_pool(pool_path: Path, kind: str, ref: str) -> None:
    """从 pool 删除 (kind,ref) 命中行(继承语义②:判完即出池)。"""
    pool_path = Path(pool_path)
    rows = [r for r in load_pool(pool_path)
            if (r.get("kind"), r.get("ref")) != (kind, ref)]
    pool_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")


def persist_envelope(sink: Path, env: dict) -> bool:
    """append 信封到 sink;按 idem_key 幂等。已存在→返回 False 不写。"""
    sink = Path(sink)
    seen = set()
    if sink.exists():
        for line in sink.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line).get("idem_key"))
    if env.get("idem_key") in seen:
        return False
    with open(sink, "a", encoding="utf-8") as f:
        f.write(json.dumps(env, ensure_ascii=False) + "\n")
    return True


def main(pool_path=POOL, sink=VERDICTS_SINK):
    import os
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT "pipelineRef","pipelineKind","verdict","corrections",'
            '"reviewer","note","verdictAt" '
            'FROM "L1ReviewQueue" '
            'WHERE "verdict" IS NOT NULL AND "syncedBack" = false')
        n = 0
        for ref, kind, verdict, corrections, reviewer, note, vat in cur.fetchall():
            # decided_run 用 verdictAt(人裁决时刻),使 idem_key=kind:ref:verdictAt
            # 稳定且每次裁决唯一;不用 runLabel(那是 pipeline 入池标签)。
            decided = vat.isoformat() if vat else ""
            raw = {"ref": ref, "kind": kind, "verdict": verdict,
                   "corrections": corrections, "reviewer": reviewer,
                   "note": note, "decided_run": decided}
            env = wrap_verdict(raw, decided_at=decided)
            if persist_envelope(sink, env):
                remove_from_pool(Path(pool_path), kind, ref)  # 继承语义②
                cur.execute(
                    'UPDATE "L1ReviewQueue" SET "syncedBack" = true '
                    'WHERE "dedupeKey" = %s', (f"{kind}::{ref}",))
                n += 1
        conn.commit()
        print(f"reverse polled {n} verdicts → {sink} "
              f"(重核 + review GC 在 applier,见 handoff)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
