"""Commentary reverse-discovery backfill.

评论里提到但尚未采集的政策,先写仓内派生候选;apply 时才复用 L1
fetch/gate/extract/ingest 流水线补采。有 URL 的可自动过门,仅标题的进 review pool。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from . import review_pool
from .dedup import DedupIndex
from .policy_gate import gate_one
from .route_interpretations import _normalize, build_title_index, match_related
from .step2_scan import KEYWORDS
from . import step4_fetch, step4_5_extract, step5_ingest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_DIR = ROOT / "state"

GOV_POLICY_URL_RE = re.compile(r"https?://[^\s<>()\"'，。；;、]+\.gov\.cn/[^\s<>()\"'，。；;、]*")
TITLE_RE = re.compile(r"《([^》]{6,60})》")


@dataclass
class PolicyRef:
    title: str | None
    url: str | None
    source_commentary: str
    business_tag: str
    context: str


def _front_body(md_text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", md_text, re.S)
    if not m:
        return {}, md_text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, m.group(2)


def _context(text: str, start: int, end: int, span: int = 100) -> str:
    return text[max(0, start - span): min(len(text), end + span)]


def _clean_url(url: str) -> str:
    return url.rstrip(".,，。；;、)")


def _is_policy_url(url: str) -> bool:
    p = urlparse(url)
    path = (p.path or "").strip("/")
    if not path:
        return False
    low = path.lower()
    if low in {"index.html", "index.htm"}:
        return False
    if any(part in low for part in ("search", "sousuo", "so.html")):
        return False
    return True


def extract_policy_refs(md_text: str, source: str) -> list[PolicyRef]:
    """从一篇评论(frontmatter+body)抽 gov 政策 URL + 《》标题,带 business_tag/context。"""
    fm, body = _front_body(md_text)
    business_tag = str(fm.get("business_tag") or "cross")
    refs: list[PolicyRef] = []
    for m in TITLE_RE.finditer(body):
        refs.append(PolicyRef(
            title=m.group(1).strip(),
            url=None,
            source_commentary=source,
            business_tag=business_tag,
            context=_context(body, m.start(), m.end()),
        ))
    for m in GOV_POLICY_URL_RE.finditer(body):
        url = _clean_url(m.group(0))
        if not _is_policy_url(url):
            continue
        refs.append(PolicyRef(
            title=None,
            url=url,
            source_commentary=source,
            business_tag=business_tag,
            context=_context(body, m.start(), m.end()),
        ))
    return refs


def is_in_scope(ref: PolicyRef) -> bool:
    """相关性闸:标题或上下文命中 L1 能源范围词才允许补采。"""
    text = f"{ref.title or ''}\n{ref.context or ''}"
    return any(kw in text for kw in KEYWORDS)


def is_already_collected(ref: PolicyRef, dedup, title_index) -> bool:
    """URL 命中 dedup,或 title 经 match_related 命中 title_index → 已采。"""
    if ref.url and dedup.is_dup(url=ref.url, official_number="", title=""):
        return True
    if ref.title:
        pid, _ = match_related(ref.title, title_index)
        if pid:
            return True
    return False


def _candidate_key(ref: PolicyRef) -> str:
    if ref.url:
        return f"url:{ref.url}"
    return f"title:{_normalize(ref.title or '')}"


def _iter_commentary_files(commentaries_dir: Path) -> list[Path]:
    return sorted(Path(commentaries_dir).glob("*.md"))


def find_backfill_candidates(commentaries_dir: Path, dedup, title_index) -> list[PolicyRef]:
    """遍历 commentaries/*.md → 抽 refs → 去已采 → 过相关性闸 → 按 (url or norm title) 去重。"""
    out: list[PolicyRef] = []
    seen: set[str] = set()
    for path in _iter_commentary_files(commentaries_dir):
        refs = extract_policy_refs(path.read_text(encoding="utf-8", errors="ignore"), path.name)
        for ref in refs:
            if is_already_collected(ref, dedup, title_index):
                continue
            if not is_in_scope(ref):
                continue
            key = _candidate_key(ref)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(ref)
    return out


def _discovery_stats(commentaries_dir: Path, dedup, title_index) -> tuple[list[PolicyRef], dict]:
    candidates: list[PolicyRef] = []
    seen: set[str] = set()
    dropped_irrelevant = 0
    files = _iter_commentary_files(commentaries_dir)
    for path in files:
        refs = extract_policy_refs(path.read_text(encoding="utf-8", errors="ignore"), path.name)
        for ref in refs:
            if is_already_collected(ref, dedup, title_index):
                continue
            if not is_in_scope(ref):
                dropped_irrelevant += 1
                continue
            key = _candidate_key(ref)
            if not key or key in seen:
                continue
            seen.add(key)
            candidates.append(ref)
    return candidates, {"scanned_commentaries": len(files), "dropped_irrelevant": dropped_irrelevant}


def _count_dropped_irrelevant(commentaries_dir: Path, dedup, title_index) -> int:
    dropped = 0
    for path in _iter_commentary_files(commentaries_dir):
        refs = extract_policy_refs(path.read_text(encoding="utf-8", errors="ignore"), path.name)
        for ref in refs:
            if not is_already_collected(ref, dedup, title_index) and not is_in_scope(ref):
                dropped += 1
    return dropped


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _candidate_row(ref: PolicyRef) -> dict:
    row = asdict(ref)
    row.update({
        "title": ref.title or "",
        "url": ref.url or "",
        "date_hint": "",
        "source_channel": "commentary_backfill",
        "city": "",
        "city_code": "",
        "province": "",
        "channel_type": ref.business_tag,
    })
    return row


def _queue_title_only(ref: PolicyRef) -> bool:
    return review_pool.append({
        "kind": "reverse_discovery",
        "ref": _normalize(ref.title or ""),
        "reason": "commentary_title_only_uncollected",
        "suggested_action": "collect",
        "confidence": None,
        "evidence": f"{ref.source_commentary} {ref.title or ''}"[:80],
        "channel": ref.business_tag,
        "run_label": "commentary_backfill",
    })


def _filter_fetched_for_gate(fetch_dir: Path, gated_dir: Path, url_refs: dict[str, PolicyRef], llm_fn) -> int:
    gated_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    for f in fetch_dir.glob("*.json"):
        row = json.loads(f.read_text(encoding="utf-8"))
        url = row.get("url", "")
        ref = url_refs.get(url) or PolicyRef(row.get("title") or None, url, "", "", row.get("body", "")[:200])
        title = row.get("title") or ref.title or ""
        body = row.get("body") or ""
        gr = gate_one(ref=url or title, url=url, title=title, body_head=body[:800], llm_fn=llm_fn)
        fetched_ref = PolicyRef(title=title, url=url, source_commentary=ref.source_commentary,
                                business_tag=ref.business_tag, context=f"{title}\n{body[:500]}")
        if gr.action != "pass" or not is_in_scope(fetched_ref):
            continue
        shutil.copyfile(f, gated_dir / f.name)
        kept += 1
    return kept


def run_backfill(commentaries_dir: Path, vault_policies: Path, *,
                 dry_run: bool = True, llm_fn=None, state_dir: Path = DEFAULT_STATE_DIR) -> dict:
    """Build commentary candidates and optionally apply URL backfill.

    默认只写 state/l1_backfill/from_commentary.jsonl。apply 时 URL 候选走
    fetch → gate → extract → ingest_extracted(out_dir=vault_policies);仅标题候选进 review pool。
    """
    commentaries_dir = Path(commentaries_dir)
    vault_policies = Path(vault_policies)
    state_dir = Path(state_dir)
    backfill_dir = state_dir / "l1_backfill"

    dedup = DedupIndex.from_vault_policies(vault_policies)
    title_index = build_title_index(skip_paths=set(), vault_root=vault_policies.parent.parent)
    candidates = find_backfill_candidates(commentaries_dir, dedup, title_index)
    candidate_path = backfill_dir / "from_commentary.jsonl"
    _write_jsonl(candidate_path, [_candidate_row(ref) for ref in candidates])

    stats = {
        "scanned_commentaries": len(_iter_commentary_files(commentaries_dir)),
        "dropped_irrelevant": _count_dropped_irrelevant(commentaries_dir, dedup, title_index),
        "candidates": len(candidates),
        "url_collected": 0,
        "queued_title_only": 0,
    }
    if dry_run:
        return stats

    title_only = [ref for ref in candidates if not ref.url and ref.title]
    for ref in title_only:
        if _queue_title_only(ref):
            stats["queued_title_only"] += 1

    url_candidates = [ref for ref in candidates if ref.url]
    if not url_candidates:
        return stats

    url_candidate_path = backfill_dir / "url_candidates.jsonl"
    _write_jsonl(url_candidate_path, [_candidate_row(ref) for ref in url_candidates])
    fetch_dir = backfill_dir / "fetch"
    gated_dir = backfill_dir / "fetch_gate_pass"
    ext_dir = backfill_dir / "extracted"
    step4_fetch.fetch_candidates(url_candidate_path, fetch_dir, backfill_dir / "fetch_errors.txt")
    kept = _filter_fetched_for_gate(fetch_dir, gated_dir, {ref.url: ref for ref in url_candidates if ref.url}, llm_fn)
    if kept == 0:
        return stats
    extracted, _ = step4_5_extract.extract_all(gated_dir, ext_dir, backfill_dir / "quarantine.jsonl")
    if extracted == 0:
        return stats
    ingested, _, _ = step5_ingest.ingest_extracted(ext_dir, backfill_dir / "ingest.jsonl", out_dir=vault_policies)
    stats["url_collected"] = ingested
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Backfill policies discovered from commentary references.")
    parser.add_argument("--commentaries-dir", required=True, type=Path)
    parser.add_argument("--vault-policies", required=True, type=Path)
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR, type=Path)
    parser.add_argument("--apply", action="store_true", help="Run fetch/gate/extract/ingest. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Explicit no-op flag; dry-run is already the default.")
    args = parser.parse_args(argv)

    stats = run_backfill(
        args.commentaries_dir,
        args.vault_policies,
        dry_run=not args.apply,
        state_dir=args.state_dir,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    candidate_path = args.state_dir / "l1_backfill" / "from_commentary.jsonl"
    if candidate_path.exists():
        rows = [line for line in candidate_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in rows[:5]:
            print(line)


if __name__ == "__main__":
    main()
