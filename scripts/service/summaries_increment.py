"""policy_summaries 增量生产者。

本模块只做本地增量编排与 policy_summaries apply:
- init-ledger 规范化建设期摘要产物并建立 pid ledger。
- run 对 ledger 外的新政策生成摘要,先写 staging,再按 apply 闸 append vault。
- produce_and_push 不在本模块内,由调用方负责。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from scripts.service.notify import send_text

PID_LEDGER = "summaries_pid_ledger.json"
SUMMARY_PATH = Path("1_extracted") / "policy_summaries.jsonl"
QUARANTINE = "summaries_quarantine.jsonl"
STAGING = "summaries_staging.jsonl"
REVIEW_QUEUE = "summaries_review_queue.jsonl"
EXTRACTED_BY = "scripts/service/summaries_increment.py"


@dataclass(frozen=True)
class PolicyDoc:
    policy_id: str
    title: str
    issuer: object
    date: object
    aliases: tuple[str, ...]
    body: str
    path: Path


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_pid_ledger(path: Path, covered: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"covered": list(covered), "updated_at": _now_iso()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _split_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    frontmatter = yaml.safe_load(parts[1]) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, parts[2].lstrip("\n")


def _normalize_aliases(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raw = str(value).strip()
    return (raw,) if raw else ()


def _load_policy_doc(path: Path) -> PolicyDoc | None:
    fm, body = _split_markdown(path)
    pid = str(fm.get("id") or "").strip()
    if not pid:
        return None
    return PolicyDoc(
        policy_id=pid,
        title=str(fm.get("title") or ""),
        issuer=fm.get("issuer"),
        date=fm.get("date"),
        aliases=_normalize_aliases(fm.get("aliases")),
        body=body,
        path=path,
    )


def _tracked_policy_files(vault: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(vault), "-c", "core.quotePath=false", "ls-files", "--", "0_raw/policies/*.md"],
            check=True,
            capture_output=True,
            text=True,
        )
        files = [vault / line for line in result.stdout.splitlines() if line.strip()]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return sorted((vault / "0_raw" / "policies").glob("*.md"))


def _tracked_policy_docs(vault: Path) -> list[PolicyDoc]:
    docs: list[PolicyDoc] = []
    seen: set[str] = set()
    for path in _tracked_policy_files(vault):
        doc = _load_policy_doc(path)
        if doc is None or doc.policy_id in seen:
            continue
        docs.append(doc)
        seen.add(doc.policy_id)
    return docs


def _policy_id_maps(vault: Path) -> tuple[dict[str, PolicyDoc], dict[str, str]]:
    docs = _tracked_policy_docs(vault)
    by_pid = {doc.policy_id: doc for doc in docs}
    alias_to_pid: dict[str, str] = {}
    for doc in docs:
        for alias in doc.aliases:
            alias_to_pid.setdefault(alias, doc.policy_id)
    return by_pid, alias_to_pid


def _latest_key(row: dict) -> str:
    return str(row.get("extracted_at") or "")


def init_ledger(vault: Path, state_dir: Path, apply: bool = False) -> dict:
    vault = Path(vault)
    state_dir = Path(state_dir)
    summary_path = vault / SUMMARY_PATH
    by_pid, alias_to_pid = _policy_id_maps(vault)

    kept_direct = 0
    kept_alias = 0
    quarantined: list[dict] = []
    mapped_rows: list[dict] = []

    for row in _iter_jsonl(summary_path):
        original_pid = str(row.get("policy_id") or "")
        if original_pid in by_pid:
            kept_direct += 1
            mapped_rows.append(dict(row))
            continue
        current_pid = alias_to_pid.get(original_pid)
        if current_pid and current_pid in by_pid:
            kept_alias += 1
            new_row = dict(row)
            new_row["policy_id"] = current_pid
            new_row["normalized_from"] = original_pid
            mapped_rows.append(new_row)
            continue
        quarantined.append({**row, "reason": "policy_id_not_found"})

    dedup: dict[str, dict] = {}
    dedup_dropped = 0
    for row in mapped_rows:
        pid = str(row.get("policy_id") or "")
        if pid in dedup:
            dedup_dropped += 1
            if _latest_key(row) > _latest_key(dedup[pid]):
                dedup[pid] = row
        else:
            dedup[pid] = row

    normalized = [dedup[pid] for pid in sorted(dedup)]
    report = {
        "kept_direct": kept_direct,
        "kept_alias": kept_alias,
        "quarantined": len(quarantined),
        "dedup_dropped": dedup_dropped,
        "covered": len(normalized),
    }
    if apply:
        _write_jsonl(summary_path, normalized)
        _write_jsonl(state_dir / QUARANTINE, quarantined)
        write_pid_ledger(state_dir / PID_LEDGER, [row["policy_id"] for row in normalized])
    return report


def _build_client(model: str, provider: str, log_path: Path):
    if provider != "openai":
        raise ValueError(f"unsupported provider: {provider}")
    from scripts.common.llm import OpenAICompatClient

    return OpenAICompatClient(model=model, log_path=str(log_path))


def _safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def _gate(row: dict) -> list[str]:
    errors: list[str] = []
    for key in ("summary", "summary_one_liner", "reading_value"):
        if not str(row.get(key) or "").strip():
            errors.append(f"{key}_empty")
    if len(str(row.get("summary") or "")) > 400:
        errors.append("summary_too_long")
    if len(str(row.get("summary_one_liner") or "")) > 25:
        errors.append("summary_one_liner_too_long")
    if len(str(row.get("reading_value") or "")) > 25:
        errors.append("reading_value_too_long")
    return errors


def _prompt(doc: PolicyDoc) -> tuple[str, str]:
    system = (
        "你是政策资料库的客观摘要生成器。只输出 JSON,字段为 summary、summary_one_liner、reading_value。"
        "summary 必须是 2-3 句客观摘要,说明范围、对象、截止日、数量目标等原文明确事项;"
        "summary_one_liner 不超过25个汉字;reading_value 不超过25个汉字。不得输出业务建议。"
    )
    user = json.dumps(
        {
            "policy_id": doc.policy_id,
            "title": doc.title,
            "issuer": doc.issuer,
            "date": doc.date,
            "body_head": doc.body[:3000],
        },
        ensure_ascii=False,
    )
    return system, user


def _generate_row(doc: PolicyDoc, client, model: str) -> tuple[dict | None, list[str], str]:
    last_errors: list[str] = []
    for _attempt in range(2):
        system, user = _prompt(doc)
        try:
            data = _safe_json(client.complete(system, user, max_tokens=1024))
            row = {
                "policy_id": doc.policy_id,
                "summary": str(data.get("summary") or "").strip(),
                "summary_one_liner": str(data.get("summary_one_liner") or "").strip(),
                "reading_value": str(data.get("reading_value") or "").strip(),
                "extracted_at": _now_iso(),
                "extracted_by": EXTRACTED_BY,
                "extracted_model": getattr(client, "model", model),
            }
            last_errors = _gate(row)
            if not last_errors:
                return row, [], ""
        except Exception as exc:  # noqa: BLE001 - LLM output failures go to review queue.
            last_errors = [f"invalid_json:{exc}"]
    return None, last_errors, ";".join(last_errors)


def _current_vault_pids(summary_path: Path) -> set[str]:
    return {str(row.get("policy_id") or "") for row in _iter_jsonl(summary_path)}


def run_increment(
    vault: Path,
    state_dir: Path,
    model: str,
    provider: str = "openai",
    *,
    dry_run: bool = False,
    limit: int | None = None,
    client=None,
) -> dict:
    vault = Path(vault)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    summary_path = vault / SUMMARY_PATH
    ledger_path = state_dir / PID_LEDGER
    staging_path = state_dir / STAGING

    tracked_docs = _tracked_policy_docs(vault)
    ledger = _load_json(ledger_path, {"covered": []})
    covered = set(ledger.get("covered") or [])
    new_docs = [doc for doc in tracked_docs if doc.policy_id not in covered]
    if limit is not None:
        new_docs = new_docs[:limit]

    staged_rows = list(_iter_jsonl(staging_path))
    staged_pids = {str(row.get("policy_id") or "") for row in staged_rows}
    generated = 0
    queued = 0
    llm = client or _build_client(model, provider, state_dir / "summaries_llm_calls.jsonl")

    for doc in new_docs:
        if doc.policy_id in staged_pids:
            continue
        row, errors, reason = _generate_row(doc, llm, model)
        if row is None:
            queued += 1
            _append_jsonl(
                state_dir / REVIEW_QUEUE,
                [{"policy_id": doc.policy_id, "reason": reason or ",".join(errors), "queued_at": _now_iso()}],
            )
            continue
        staged_rows.append(row)
        staged_pids.add(doc.policy_id)
        generated += 1

    _write_jsonl(staging_path, staged_rows)
    new_pids = {doc.policy_id for doc in new_docs}
    staged_for_new = [row for row in staged_rows if str(row.get("policy_id") or "") in new_pids]
    summary = {
        "new": len(new_docs),
        "generated": generated,
        "queued": queued,
        "staged": len(staged_for_new),
        "applied": False,
    }
    if dry_run:
        return summary

    existing_rows = list(_iter_jsonl(summary_path))
    existing_pids = [str(row.get("policy_id") or "") for row in existing_rows]
    existing_pid_set = set(existing_pids)
    append_rows = [row for row in staged_for_new if str(row.get("policy_id") or "") not in existing_pid_set]
    candidate_rows = existing_rows + append_rows
    candidate_pids = [str(row.get("policy_id") or "") for row in candidate_rows]
    if len(candidate_pids) != len(set(candidate_pids)) or len(candidate_rows) != len(existing_rows) + len(append_rows):
        reason = "policy_summaries apply gate refused: duplicate policy_id or row count mismatch"
        send_text(f"[S2] 摘要增量 apply gate refused: {reason}")
        print(json.dumps({"error": reason, **summary}, ensure_ascii=False))
        raise SystemExit(1)

    _write_jsonl(summary_path, candidate_rows)
    covered_list = list(ledger.get("covered") or [])
    covered_set = set(covered_list)
    for row in append_rows:
        pid = str(row.get("policy_id") or "")
        if pid not in covered_set:
            covered_list.append(pid)
            covered_set.add(pid)
    write_pid_ledger(ledger_path, covered_list)
    applied_pids = {str(row.get("policy_id") or "") for row in append_rows}
    _write_jsonl(staging_path, [row for row in staged_rows if str(row.get("policy_id") or "") not in applied_pids])
    summary["applied"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="policy_summaries 增量生产者")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-ledger")
    p_init.add_argument("--vault", type=Path, required=True)
    p_init.add_argument("--state-dir", type=Path, required=True)
    p_init.add_argument("--apply", action="store_true")

    p_run = sub.add_parser("run")
    p_run.add_argument("--vault", type=Path, required=True)
    p_run.add_argument("--state-dir", type=Path, required=True)
    p_run.add_argument("--model", required=True)
    p_run.add_argument("--provider", default="openai")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--limit", type=int)

    args = ap.parse_args(argv)
    if args.cmd == "init-ledger":
        result = init_ledger(args.vault, args.state_dir, apply=args.apply)
    elif args.cmd == "run":
        result = run_increment(
            args.vault,
            args.state_dir,
            args.model,
            args.provider,
            dry_run=args.dry_run,
            limit=args.limit,
        )
    else:
        raise SystemExit(f"unsupported command: {args.cmd}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
