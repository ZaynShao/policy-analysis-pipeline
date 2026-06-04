# Analysis High Precision Relations Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ③-B high precision policy relation preview for deterministic `references`, `cites_basis`, `supersedes`, and `clarifies` candidates.

**Architecture:** Add `scripts/analysis_high_precision_relations` with a preview CLI. It reads only git tracked raw policy markdown, indexes `official_number`, scans current policy bodies, classifies high precision candidate rows, and writes JSON/JSONL plus a Chinese HTML report under `state/analysis_layer/preview_20260604/`.

**Tech Stack:** Python standard library, pytest, existing `python3 -m scripts.<tool>.run` CLI pattern.

---

## Files

- Create: `scripts/analysis_high_precision_relations/__init__.py`
- Create: `scripts/analysis_high_precision_relations/run.py`
- Create: `scripts/analysis_high_precision_relations/report.py`
- Create: `tests/analysis_high_precision_relations/__init__.py`
- Create: `tests/analysis_high_precision_relations/test_run.py`
- Create live state under: `state/analysis_layer/preview_20260604/`
- Modify: `docs/BACKLOG.md`

## Task 1: Add Failing Tests

**Files:**
- Create: `tests/analysis_high_precision_relations/__init__.py`
- Create: `tests/analysis_high_precision_relations/test_run.py`

- [ ] **Step 1: Test tracked raw and basis references**

Create a temp vault git repo with a tracked target policy carrying `official_number: 发改能源〔2025〕357号`, a tracked source policy whose opening says `根据《...》（发改能源〔2025〕357号）...结合实际制定本办法`, and one untracked policy. Assert preview reports `tracked_policy_count == 2`, `untracked_policy_count == 1`, and emits both `references` and `cites_basis` for the source/target pair.

- [ ] **Step 2: Test supersedes and clarifies**

Create tracked target/source policies where source text says `《旧规则》（发改能源规〔2020〕889号）同时废止`, and a separate source titled `某政策实施细则` referencing a target doc number. Assert output includes `supersedes` and `clarifies` candidates with evidence.

- [ ] **Step 3: Test output files**

Assert preview writes:

- `high_precision_relation_summary.json`
- `high_precision_relation_candidates.jsonl`
- `policy_relation_candidates/references.jsonl`
- `policy_relation_candidates/cites_basis.jsonl`
- `policy_relation_candidates/supersedes.jsonl`
- `policy_relation_candidates/clarifies.jsonl`
- `reports/high_precision_relation_preview.html`

- [ ] **Step 4: Run red tests**

Run:

```bash
python3 -m pytest -q tests/analysis_high_precision_relations
```

Expected: fail because `scripts.analysis_high_precision_relations` does not exist yet.

## Task 2: Implement Preview CLI

**Files:**
- Create: `scripts/analysis_high_precision_relations/__init__.py`
- Create: `scripts/analysis_high_precision_relations/run.py`
- Create: `scripts/analysis_high_precision_relations/report.py`

- [ ] **Step 1: Implement tracked policy loading**

Use `git -C <vault> -c core.quotePath=false ls-files -- '0_raw/policies/*.md'` for the baseline and `git ls-files --others --exclude-standard` for the excluded raw count.

- [ ] **Step 2: Implement frontmatter/body parsing**

Parse `id`, `aliases`, `title`, and `official_number` from the first frontmatter block, and keep the body after the closing `---`.

- [ ] **Step 3: Implement official-number index**

Index non-empty official numbers to current tracked target policies. Ignore empty official numbers and self-links.

- [ ] **Step 4: Implement candidate classification**

Emit:

- `references` for any target official number match.
- `cites_basis` when the match is in opening 800 chars and the evidence window contains basis keywords.
- `supersedes` when the evidence window contains supersession keywords.
- `clarifies` when the source title or evidence window contains clarification keywords.

Deduplicate by `from/to/rel/doc_number`.

- [ ] **Step 5: Implement summary and HTML**

Summary includes tracked/untracked raw counts, candidate count, counts by relation, and notes: preview only, no vault write, no raw write, no model call.

- [ ] **Step 6: Run green tests**

Run:

```bash
python3 -m pytest -q tests/analysis_high_precision_relations
```

Expected: pass.

## Task 3: Run Live Preview

**Files:**
- Create: `state/analysis_layer/preview_20260604/high_precision_relation_summary.json`
- Create: `state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl`
- Create: `state/analysis_layer/preview_20260604/policy_relation_candidates/*.jsonl`
- Create: `state/analysis_layer/preview_20260604/reports/high_precision_relation_preview.html`

- [ ] **Step 1: Run preview**

Run:

```bash
python3 -m scripts.analysis_high_precision_relations.run preview \
  --vault "/Users/shaoziyuan/Documents/Zayn Main/政策分析" \
  --state state/analysis_layer/preview_20260604
```

Expected: state files and Chinese HTML are created. Report must state it did not write vault/raw and did not call a model.

- [ ] **Step 2: Update backlog**

Modify `docs/BACKLOG.md` B10 with ③-B preview progress and counts.

## Task 4: Verify and Commit

**Files:**
- Commit all created and modified engineering files.

- [ ] **Step 1: Verify**

Run:

```bash
python3 -m pytest -q tests/analysis_high_precision_relations
python3 -m pytest -q
python3 -m scripts.audit.principle_guard scripts/analysis_high_precision_relations scripts/l2_themescore
git diff --check
git -C "/Users/shaoziyuan/Documents/Zayn Main/政策分析" status --short --branch
```

Expected:

- tests pass
- principle guard passes
- vault remains unchanged except the known pre-existing untracked raw file

- [ ] **Step 2: Commit and push**

Run:

```bash
git add docs/BACKLOG.md \
  docs/superpowers/specs/2026-06-04-analysis-high-precision-relations-design.md \
  docs/superpowers/plans/2026-06-04-analysis-high-precision-relations-preview.md \
  scripts/analysis_high_precision_relations tests/analysis_high_precision_relations
git add -f state/analysis_layer/preview_20260604/high_precision_relation_summary.json \
  state/analysis_layer/preview_20260604/high_precision_relation_candidates.jsonl \
  state/analysis_layer/preview_20260604/policy_relation_candidates \
  state/analysis_layer/preview_20260604/reports/high_precision_relation_preview.html
git commit -m "feat: add high precision relation preview"
git push
```

Expected: engineering repo is clean and pushed.
