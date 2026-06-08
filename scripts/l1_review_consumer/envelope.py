"""B14 标准信封:把 L1 的 OUT 裁决记录包成跨池统一格式。

L1 OUT 记录:{ref, kind, verdict, corrections?, reviewer, note, decided_run}
B14 在外面补:envelope_v / pool / decided_at / idem_key / applied 审计三件套。
verdict 合法性按 L1 的 VERDICTS 校验(单一真相源,不另立枚举)。
"""
from scripts.l1_collect.review_pool import VERDICTS

ENVELOPE_V = 1
POOL = "l1_source_quality"


def wrap_verdict(raw: dict, decided_at: str) -> dict:
    """包一条人审裁决成标准信封。decided_at 由调用方传(ISO8601)。

    raise ValueError:kind 未知 / verdict 不在该 kind 的允许集。
    """
    kind = raw["kind"]
    verdict = raw["verdict"]
    if kind not in VERDICTS:
        raise ValueError(f"unknown kind: {kind!r}; allowed={tuple(VERDICTS)}")
    if verdict not in VERDICTS[kind]:
        raise ValueError(
            f"bad verdict {verdict!r} for kind {kind!r}; allowed={VERDICTS[kind]}")
    ref = raw["ref"]
    decided_run = raw.get("decided_run") or ""
    return {
        "envelope_v": ENVELOPE_V,
        "pool": POOL,
        "ref": ref,
        "kind": kind,
        "verdict": verdict,
        "corrections": raw.get("corrections") or {},
        "reviewer": raw.get("reviewer", ""),
        "note": raw.get("note", ""),
        "decided_run": decided_run,
        "decided_at": decided_at,
        "idem_key": f"{kind}:{ref}:{decided_run}",
        "applied": False,
        "applied_at": None,
        "apply_result": None,
    }
