import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from .theme_registry import ThemeRegistry


SCHEMA_VERSION = "node2b_manual_decision.v1"
DEFAULT_REGISTRY = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "_meta" / "themes_registry.yaml"
DECISIONS = {
    "candidate_accept",
    "zero_or_weak_trend",
    "keep_manual",
    "custom",
}


def _json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_sha256(row: dict) -> str:
    return hashlib.sha256(_json_dumps(row).encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _extract_evidence_sections(report_path: Path) -> dict:
    if not report_path.exists():
        return {}
    text = report_path.read_text(encoding="utf-8")
    sections = {}
    pattern = re.compile(
        r"(<section>\s*<h2><span class=\"pid\">(?P<pid>[^<]+)</span>.*?</section>)",
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        sections[html.unescape(match.group("pid"))] = match.group(1)
    return sections


PathLike = Union[str, Path]


def load_decisions(state: PathLike) -> list:
    return _read_jsonl(Path(state) / "manual_decisions.jsonl")


def _latest_decisions_by_pid(state: Path) -> dict:
    latest = {}
    for row in load_decisions(state):
        latest[row.get("pid", "")] = row
    return latest


def load_review_items(state: PathLike) -> list:
    state = Path(state)
    queue_path = state / "review_queue" / "queue.jsonl"
    report_path = state / "reports" / "manual_review_pool_zh.html"
    sections = _extract_evidence_sections(report_path)
    latest = _latest_decisions_by_pid(state)
    items = []
    for idx, row in enumerate(_read_jsonl(queue_path)):
        pid = row["pid"]
        evidence_html = sections.get(pid) or (
            f"<section><h2>{html.escape(pid)}</h2>"
            "<p class=\"missing\">未找到证据 HTML,请回到 manual_review_pool_zh.html 检查。</p></section>"
        )
        items.append({
            "pid": pid,
            "queue_index": idx,
            "queue_stage": row.get("stage", ""),
            "queue_reason": row.get("reason", ""),
            "queue_detail": row.get("detail", {}),
            "queue_path": str(queue_path.resolve()),
            "queue_record": row,
            "queue_record_sha256": _record_sha256(row),
            "evidence_report": str(report_path.resolve()),
            "evidence_html": evidence_html,
            "existing_decision": latest.get(pid),
        })
    return items


def is_manual_adjudication_stage(stage: str) -> bool:
    return stage == "judge_reject"


def split_review_items(items: list) -> tuple:
    manual = [item for item in items if is_manual_adjudication_stage(item["queue_stage"])]
    technical = [item for item in items if not is_manual_adjudication_stage(item["queue_stage"])]
    return manual, technical


def load_theme_options(registry_path: Optional[PathLike] = None) -> list:
    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY
    if not path.exists():
        return []
    registry = ThemeRegistry.load(str(path))
    return [{"id": tid, "label": registry.zh.get(tid, tid)} for tid in registry.ids]


def _normalize_themes(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _normalize_importance(value):
    if value in (None, ""):
        return None
    return int(value)


def make_decision_record(
    state: PathLike,
    item: dict,
    payload: dict,
    now_iso: Optional[str] = None,
    operator: str = "local_user",
    theme_options: Optional[list] = None,
) -> dict:
    decision = payload.get("decision")
    if decision not in DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    now_iso = now_iso or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    target_themes = _normalize_themes(payload.get("target_theme_ids", payload.get("target_themes")))
    primary_theme = str(payload.get("primary_theme_id", payload.get("primary_theme") or "")).strip()
    label_by_id = {x["id"]: x["label"] for x in (theme_options or [])}
    record = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso,
        "operator": operator,
        "decision_source": "localhost_manual_review",
        "state_dir": str(Path(state).resolve()),
        "pid": item["pid"],
        "queue_index": item["queue_index"],
        "queue_stage": item["queue_stage"],
        "queue_reason": item["queue_reason"],
        "queue_detail": item["queue_detail"],
        "queue_path": item["queue_path"],
        "queue_record_sha256": item["queue_record_sha256"],
        "evidence_report": item["evidence_report"],
        "decision": decision,
        "target_themes": target_themes,
        "target_theme_labels": [label_by_id.get(tid, tid) for tid in target_themes],
        "primary_theme": primary_theme,
        "primary_theme_label": label_by_id.get(primary_theme, primary_theme),
        "importance": _normalize_importance(payload.get("importance")),
        "note": str(payload.get("note") or "").strip(),
        "flow_assertion": "entered_via_review_queue_then_human_adjudicated",
    }
    decision_basis = {
        "pid": record["pid"],
        "created_at": record["created_at"],
        "queue_record_sha256": record["queue_record_sha256"],
        "decision": record["decision"],
        "target_themes": record["target_themes"],
        "primary_theme": record["primary_theme"],
        "importance": record["importance"],
        "note": record["note"],
    }
    record["decision_id"] = hashlib.sha256(_json_dumps(decision_basis).encode("utf-8")).hexdigest()
    return record


def append_decision(state: PathLike, record: dict) -> Path:
    out = Path(state) / "manual_decisions.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out


def _json_script(data) -> str:
    raw = json.dumps(data, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def render_app(state: PathLike, registry_path: Optional[PathLike] = None) -> str:
    state = Path(state)
    all_items = load_review_items(state)
    items, technical_items = split_review_items(all_items)
    theme_options = load_theme_options(registry_path)
    decisions_path = state / "manual_decisions.jsonl"
    cases = "\n".join(
        f"""<article class="case" data-index="{i}">
<div class="case-head">
<div><span class="pid">{html.escape(item['pid'])}</span><span class="stage">{html.escape(item['queue_stage'])}</span></div>
<code>queue_record_sha256: {html.escape(item['queue_record_sha256'])}</code>
</div>
<div class="reason">{html.escape(item['queue_reason'])}</div>
<div class="evidence">{item['evidence_html']}</div>
</article>"""
        for i, item in enumerate(items)
    )
    technical_rows = "\n".join(
        f"""<tr><td>{html.escape(item['pid'])}</td><td>{html.escape(item['queue_stage'])}</td><td>{html.escape(item['queue_reason'])}</td><td><code>{html.escape(item['queue_record_sha256'])}</code></td></tr>"""
        for item in technical_items
    )
    theme_buttons = "\n".join(
        f"""<button type="button" class="chip" data-role="theme-option" data-theme-id="{html.escape(opt['id'])}">{html.escape(opt['label'])}</button>"""
        for opt in theme_options
    )
    primary_buttons = "\n".join(
        f"""<button type="button" class="chip" data-role="primary-option" data-theme-id="{html.escape(opt['id'])}">{html.escape(opt['label'])}</button>"""
        for opt in theme_options
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>②-B 人工裁决台</title>
<style>
:root{{color-scheme:light;--bg:#f6f7f9;--fg:#172033;--muted:#64748b;--line:#d8dee8;--panel:#fff;--accent:#155eef;--ok:#0f766e}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;line-height:1.55}}
header{{position:sticky;top:0;background:#ffffffee;border-bottom:1px solid var(--line);backdrop-filter:blur(10px);z-index:2}}
.wrap{{max-width:1180px;margin:0 auto;padding:18px 22px}} h1{{font-size:22px;margin:0 0 8px}} .sub{{color:var(--muted);font-size:13px;margin:0}}
.grid{{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px;align-items:start}} .panel,.case{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}}
.case{{display:none}} .case.active{{display:block}} .case-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:12px}}
.pid{{font-weight:700;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}} .stage{{display:inline-block;margin-left:10px;padding:2px 8px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12px}}
code{{font-size:11px;color:#475569;word-break:break-all}} .reason{{background:#fff7ed;border:1px solid #fed7aa;padding:10px;border-radius:6px;margin-bottom:14px}}
.evidence section{{border:0;padding:0;margin:0}} .evidence h2{{font-size:20px}} .evidence h3{{font-size:15px;margin-top:16px}} .evidence ul{{padding-left:20px}} .evidence li{{margin:8px 0}}
label{{display:block;font-size:13px;font-weight:600;margin-top:12px}} select,input,textarea{{width:100%;font:inherit;border:1px solid var(--line);border-radius:6px;padding:8px;background:#fff}} textarea{{min-height:92px;resize:vertical}}
.theme-grid{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px}} .chip{{text-align:left;border:1px solid var(--line);background:#fff;border-radius:6px;padding:7px 9px;cursor:pointer;font-size:13px;min-height:34px}} .chip.selected{{border-color:var(--accent);background:#eaf1ff;color:#123b91;font-weight:700}} .chip.primary-selected{{border-color:var(--ok);background:#ecfdf5;color:#065f46;font-weight:700}}
.row{{display:grid;grid-template-columns:1fr;gap:10px}} .buttons{{display:flex;gap:8px;margin-top:14px}} button{{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px 11px;cursor:pointer}} button.primary{{background:var(--accent);border-color:var(--accent);color:white}} button:disabled{{opacity:.45;cursor:not-allowed}}
.status{{margin-top:10px;color:var(--ok);font-size:13px;min-height:20px}} .audit{{font-size:12px;color:var(--muted);border-top:1px solid var(--line);margin-top:14px;padding-top:12px}}
.technical{{margin-top:18px}} .technical table{{width:100%;border-collapse:collapse;font-size:12px;background:#fff}} .technical th,.technical td{{border:1px solid var(--line);padding:7px;vertical-align:top;text-align:left}} .technical th{{background:#f1f5f9}}
</style></head><body>
<header><div class="wrap">
<h1>②-B 人工裁决台</h1>
<p class="sub">来源 <code>{html.escape(str((state / 'review_queue' / 'queue.jsonl').resolve()))}</code> · 输出 <code>{html.escape(str(decisions_path.resolve()))}</code>。只写 dry-run state,不写政策库、不 apply。</p>
<p class="sub">人工裁决项 {len(items)} 条 · 技术复跑项 {len(technical_items)} 条。只有 judge_reject 进入人工裁决; program_gate/generation_error 不要求选主题。</p>
</div></header>
<main class="wrap grid">
<section>
{cases or '<div class="panel">当前没有需要人工裁决的业务项。</div>'}
<div class="technical panel">
<h2>技术复跑项 {len(technical_items)} 条</h2>
<p class="sub">这些是程序门、结构错误或生成错误;不属于人工业务归属判断,应在技术修复后进入 bounded dry-run 复跑。</p>
<table><tr><th>PID</th><th>阶段</th><th>原因</th><th>queue hash</th></tr>{technical_rows or '<tr><td colspan="4">无</td></tr>'}</table>
</div>
</section>
<aside class="panel">
<h2 id="counter">0 / 0</h2>
<form id="decisionForm">
<label>裁决</label>
<select name="decision">
<option value="candidate_accept">候选裁决成立</option>
<option value="zero_or_weak_trend">归零/弱趋势</option>
<option value="keep_manual">继续留在人工待办</option>
<option value="custom">自定义裁决</option>
</select>
<label>业务主题（可多选）</label>
<div class="theme-grid" id="themePicker">{theme_buttons or '<span class="sub">未找到主题词表。</span>'}</div>
<div class="row">
<div><label>主主题（单选）</label><div class="theme-grid" id="primaryPicker">{primary_buttons or '<span class="sub">未找到主题词表。</span>'}</div></div>
<div><label>重要性</label><input name="importance" type="number" min="0" max="5" placeholder="0-5"></div>
</div>
<label>裁决理由/备注</label>
<textarea name="note" placeholder="说明你采纳/不采纳候选裁决的理由"></textarea>
<div class="buttons">
<button type="button" id="prevBtn">上一条</button>
<button type="submit" class="primary">保存并下一条</button>
<button type="button" id="nextBtn">下一条</button>
</div>
<div class="status" id="status"></div>
</form>
<div class="audit">每条保存都会记录 pid、入队阶段、入队原因、queue_record_sha256、operator、时间和人工裁决。复审时可从 hash 对回原始 queue 行。</div>
</aside>
</main>
<script id="items" type="application/json">{_json_script(items)}</script>
<script id="themeOptions" type="application/json">{_json_script(theme_options)}</script>
<script>
const items = JSON.parse(document.getElementById('items').textContent);
const themeOptions = JSON.parse(document.getElementById('themeOptions').textContent);
let index = 0;
const cases = [...document.querySelectorAll('.case')];
const form = document.getElementById('decisionForm');
const statusEl = document.getElementById('status');
const selectedThemes = new Set();
let primaryTheme = '';
const themeButtons = [...document.querySelectorAll('[data-role="theme-option"]')];
const primaryButtons = [...document.querySelectorAll('[data-role="primary-option"]')];
function paintThemeButtons() {{
  themeButtons.forEach(btn => btn.classList.toggle('selected', selectedThemes.has(btn.dataset.themeId)));
  primaryButtons.forEach(btn => btn.classList.toggle('primary-selected', primaryTheme === btn.dataset.themeId));
}}
function setSelection(themes, primary) {{
  selectedThemes.clear();
  (themes || []).forEach(t => selectedThemes.add(t));
  primaryTheme = primary || '';
  if (primaryTheme && !selectedThemes.has(primaryTheme)) selectedThemes.add(primaryTheme);
  paintThemeButtons();
}}
themeButtons.forEach(btn => {{
  btn.onclick = () => {{
    const id = btn.dataset.themeId;
    if (selectedThemes.has(id)) {{
      selectedThemes.delete(id);
      if (primaryTheme === id) primaryTheme = '';
    }} else {{
      selectedThemes.add(id);
    }}
    paintThemeButtons();
  }};
}});
primaryButtons.forEach(btn => {{
  btn.onclick = () => {{
    primaryTheme = btn.dataset.themeId;
    selectedThemes.add(primaryTheme);
    paintThemeButtons();
  }};
}});
function show(i) {{
  if (!items.length) return;
  index = Math.max(0, Math.min(i, items.length - 1));
  cases.forEach((el, n) => el.classList.toggle('active', n === index));
  document.getElementById('counter').textContent = `${{index + 1}} / ${{items.length}}`;
  const existing = items[index].existing_decision;
  setSelection(existing ? existing.target_themes : [], existing ? existing.primary_theme : '');
  statusEl.textContent = existing ? `已有裁决: ${{existing.decision}}` : '';
}}
document.getElementById('prevBtn').onclick = () => show(index - 1);
document.getElementById('nextBtn').onclick = () => show(index + 1);
form.onsubmit = async (event) => {{
  event.preventDefault();
  const item = items[index];
  const data = Object.fromEntries(new FormData(form).entries());
  data.target_theme_ids = [...selectedThemes];
  data.primary_theme_id = primaryTheme;
  data.pid = item.pid;
  data.queue_record_sha256 = item.queue_record_sha256;
  const res = await fetch('/api/decision', {{
    method: 'POST',
    headers: {{'content-type': 'application/json'}},
    body: JSON.stringify(data),
  }});
  const out = await res.json();
  if (!res.ok) {{
    statusEl.textContent = out.error || '保存失败';
    return;
  }}
  items[index].existing_decision = out.record;
  form.reset();
  setSelection([], '');
  statusEl.textContent = `已保存: ${{out.record.decision}}`;
  show(index + 1);
}};
show(0);
</script>
</body></html>"""


def _json_response(handler: BaseHTTPRequestHandler, status: int, data: dict):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(state: PathLike, operator: str, registry_path: Optional[PathLike] = None):
    state = Path(state)

    class ManualReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                body = render_app(state, registry_path).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/items":
                manual, technical = split_review_items(load_review_items(state))
                _json_response(self, 200, {"items": manual, "technical_items": technical})
                return
            if path == "/api/themes":
                _json_response(self, 200, {"themes": load_theme_options(registry_path)})
                return
            if path == "/api/decisions":
                _json_response(self, 200, {"decisions": load_decisions(state)})
                return
            _json_response(self, 404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path != "/api/decision":
                _json_response(self, 404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                items, _technical = split_review_items(load_review_items(state))
                item = next(
                    (
                        x for x in items
                        if x["pid"] == payload.get("pid")
                        and x["queue_record_sha256"] == payload.get("queue_record_sha256")
                    ),
                    None,
                )
                if item is None:
                    raise ValueError("payload does not match current review queue")
                record = make_decision_record(
                    state,
                    item,
                    payload,
                    operator=operator,
                    theme_options=load_theme_options(registry_path),
                )
                append_decision(state, record)
                _json_response(self, 200, {"ok": True, "record": record})
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})

    return ManualReviewHandler


def serve(state: PathLike, host: str, port: int, operator: str, registry_path: Optional[PathLike] = None):
    server = ThreadingHTTPServer((host, port), make_handler(state, operator, registry_path))
    print(f"manual-review: http://{host}:{server.server_port}/")
    print(f"state: {Path(state).resolve()}")
    server.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--operator", default="local_user")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    args = ap.parse_args()
    serve(args.state, args.host, args.port, args.operator, args.registry)


if __name__ == "__main__":
    main()
