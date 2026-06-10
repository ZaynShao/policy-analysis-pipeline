# Codex 交接(待命):L1 扫描段并发化(165 渠道串行 → 线程池)

**状态:已决定执行(2026-06-10 用户拍板「先修再跑」)。** 触发不再走 ">2h 条件"——理由升级为:① Step 2 真跑会**从头重扫**,串行扫描的一个多小时今晚要再付一遍;② dry-run 已证 cand 有 ~66 候选 = 每日 cron 常态有活,串行 L1 悬在 flock `-w 7200`(2h)→ L2/投影 跳过 的预算线边上,需并发拉开余量。**本手册是 S2 今晚链路的第一步,跑完接 `docs/handoffs/2026-06-10-codex-s2-w2w3-night.md` 的 Step 2。**

**目标**:把 `run_incremental` 的扫描段(165 个验证渠道、逐个串行 HTTP)改成线程池并发,**仅并发扫描这一只读段**,下游 filter/fetch/gate/ingest/L2 入队/vault 写**全部保持串行不变**。语义零变化,只加速。预期 ~1 小时 → 5–10 分钟。

**背景**:扫描慢的根因 = 165 渠道 × 每渠道最多 5 页(`MAX_PAGES`)× 20s 超时(`TIMEOUT`),全程串行。`scan_channel(ch, out_dir)` 已确认线程安全:只用局部变量、写各自唯一文件 `{city}__{channel_type}__{root_domain}.jsonl`、mkdir 带 exist_ok、不碰共享状态。去重索引 `DedupIndex` 在循环外建一次、只在 filter(第二段)读,扫描段不碰它。并发跨的是不同域名(每渠道不同政府站),对单站无加压;每渠道内部翻页仍串行 → 单站并发度 ≤1,礼貌。

**纪律(红线)**:
- 这是代码改动 = 走 TDD:先写失败测试 → 实现 → 全绿 → Claude 审 diff → 合 main → 服务器重建镜像。**不许跳测试、不许直接改生产容器。**
- 改动范围严格限定在 `run_incremental.py`(扫描派发)+ 对应测试。**不动** `step2_scan.py`、`filter`、`fetch`、`ingest`、L2 队列、vault 写逻辑。
- 输出顺序、L2 入队顺序、vault 写顺序**必须与串行版完全一致**(用 `ex.map` 保序 + 第二段仍按 catalog 顺序串行)。
- 凭据不进 git;仓库工作区别条线的未跟踪文件不碰。
- 若实现中发现 `scan_channel` 有任何共享可变状态(与上面判断矛盾)→ **停下报告**,不强行并发。

---

## 改点(`scripts/l1_collect/run_incremental.py`)

### 1. import(文件顶部 import 区)
```python
from concurrent.futures import ThreadPoolExecutor
```

### 2. `IncrementalConfig` 加字段
```python
    l2_queue_path: Path = STATE / "l2_queue.jsonl"
    scan_workers: int = 12          # ← 新增:扫描段并发度(I/O 密集,可 > CPU 数)
```

### 3. 新增 `_safe_scan` 包装(放在 `_run_channel` 之前)
```python
def _safe_scan(ch, scan_dir: Path) -> int:
    """单渠道扫描包装:异常→记日志返回 0,不让一个渠道拖垮并发池或中断全局。"""
    try:
        return scan_channel(ch, scan_dir)
    except Exception as e:
        print(f"  [scan 失败] {ch.city}/{ch.root_domain}: {str(e)[:80]}")
        return 0
```

### 4. `_run_channel` 去掉内联扫描,改收外部 `n_scan`
签名加 `n_scan: int`;删除内部 `n_scan = scan_channel(ch, sd / "scan")` 那一行(其余逻辑一字不动):
```python
def _run_channel(ch, cfg: IncrementalConfig, dedup, llm_fn, n_scan: int) -> dict:
    sd = cfg.state_dir
    for d in ["scan", "cand", "quar", "fetch", "ext", "passed", "comm_ext", "comm_stage", "ingest"]:
        (sd / d).mkdir(parents=True, exist_ok=True)
    label = f"{ch.city}__{ch.channel_type}__{ch.root_domain}"
    if n_scan == 0:
        return {"channel": label, "scanned": 0, "ingested": 0}
    merged = sd / "scan" / f"_merged_{ch.root_domain}.jsonl"
    # ……以下原样不变……
```

### 5. `run_incremental` 主循环前加并发预扫,循环改 zip
原:
```python
    with _l1_lock():
        dedup = DedupIndex.from_vault_policies(cfg.vault_dir)
        for ch in channels:
            r = _run_channel(ch, cfg, dedup, llm_fn)
            results.append(r)
            if not cfg.dry_run and r.get("pids"):
                enqueue_ingested(cfg.l2_queue_path, r["pids"],
                                 requested_at=datetime.now(CST).isoformat(timespec="seconds"))
            print(f"  {r['channel'][:48]:48s} scan={r['scanned']} ing={r.get('ingested',0)}")
```
改为:
```python
    with _l1_lock():
        dedup = DedupIndex.from_vault_policies(cfg.vault_dir)
        # 扫描段并发(只读 HTTP,各渠道写各自文件,线程安全);ex.map 保序
        scan_dir = cfg.state_dir / "scan"
        scan_dir.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=cfg.scan_workers) as ex:
            scan_counts = list(ex.map(lambda c: _safe_scan(c, scan_dir), channels))
        # 下游 filter/fetch/gate/ingest/入队/vault 写仍按 catalog 顺序串行
        for ch, n_scan in zip(channels, scan_counts):
            r = _run_channel(ch, cfg, dedup, llm_fn, n_scan)
            results.append(r)
            if not cfg.dry_run and r.get("pids"):
                enqueue_ingested(cfg.l2_queue_path, r["pids"],
                                 requested_at=datetime.now(CST).isoformat(timespec="seconds"))
            print(f"  {r['channel'][:48]:48s} scan={r['scanned']} ing={r.get('ingested',0)}")
```

### 6. `main()` 加 CLI(默认 12,cron 不传则用默认,无需改 cron)
```python
    ap.add_argument("--scan-workers", type=int, default=12)
    ...
    run_incremental(IncrementalConfig(
        ...,
        scan_workers=a.scan_workers,
        l2_queue_path=...,
    ))
```

---

## TDD(`tests/l1_collect/test_run_incremental.py` 追加)

先读现有文件顶部的 `_ch(level, domain)` helper 复用。两条新测试,先写、先看红、再实现:

**测试 A:保序 + n_scan 正确透传给各渠道**
```python
def test_scan_phase_preserves_order_and_passes_counts(tmp_path, monkeypatch):
    import types
    import scripts.l1_collect.run_incremental as ri
    chans = [_ch("国家", f"ch{i}.gov.cn") for i in range(5)]
    monkeypatch.setattr(ri, "load_catalog", lambda *a, **k: chans)
    monkeypatch.setattr(ri, "_select_channels", lambda *a, **k: chans)
    monkeypatch.setattr(ri, "DedupIndex",
                        types.SimpleNamespace(from_vault_policies=lambda d: None))
    monkeypatch.setattr(ri, "scan_channel", lambda ch, d: int(ch.root_domain[2]))  # ch3→3
    captured = []
    def fake_proc(ch, cfg, dedup, llm_fn, n_scan):
        captured.append((ch.root_domain, n_scan))
        return {"channel": ch.root_domain, "scanned": n_scan, "ingested": 0}
    monkeypatch.setattr(ri, "_run_channel", fake_proc)
    ri.run_incremental(ri.IncrementalConfig(
        state_dir=tmp_path, vault_dir=tmp_path, dry_run=True))
    assert captured == [(f"ch{i}.gov.cn", i) for i in range(5)]   # 顺序 + 计数都对
```

**测试 B:单渠道扫描异常被隔离成 0,不影响其它**
```python
def test_scan_failure_isolated(tmp_path, monkeypatch):
    import types
    import scripts.l1_collect.run_incremental as ri
    chans = [_ch("国家", "good.gov.cn"), _ch("国家", "bad.gov.cn"), _ch("国家", "good2.gov.cn")]
    monkeypatch.setattr(ri, "load_catalog", lambda *a, **k: chans)
    monkeypatch.setattr(ri, "_select_channels", lambda *a, **k: chans)
    monkeypatch.setattr(ri, "DedupIndex",
                        types.SimpleNamespace(from_vault_policies=lambda d: None))
    def scan(ch, d):
        if ch.root_domain == "bad.gov.cn":
            raise RuntimeError("boom")
        return 7
    monkeypatch.setattr(ri, "scan_channel", scan)
    seen = {}
    monkeypatch.setattr(ri, "_run_channel",
                        lambda ch, cfg, dedup, llm_fn, n_scan: seen.__setitem__(ch.root_domain, n_scan)
                        or {"channel": ch.root_domain, "scanned": n_scan, "ingested": 0})
    summary = ri.run_incremental(ri.IncrementalConfig(
        state_dir=tmp_path, vault_dir=tmp_path, dry_run=True))
    assert seen == {"good.gov.cn": 7, "bad.gov.cn": 0, "good2.gov.cn": 7}
    assert summary["total_scanned"] == 14
```

跑:`python -m pytest tests/l1_collect/test_run_incremental.py -v`(先红)→ 实现 → 绿 → **全量** `python -m pytest -q`(回归,确认 561 条仍绿)。

---

## 合并 + 部署(镜像必须重建——代码烤进 image,非挂载)

1. 分支:`git checkout -b perf/l1-scan-concurrent`,提交,`git push -u origin perf/l1-scan-concurrent`。把 diff 贴回聊天 **等 Claude 审过**再合。
2. 合 main(Claude/用户拍)。
3. 服务器(已在场授权下):
   ```bash
   cd /root/policy-pipeline-src && git fetch origin && git reset --hard origin/main
   docker compose -f docker-compose.server.yml build policy-producer
   docker run --rm policy-pipeline:latest python -c "import trafilatura, bs4; print('build ok')"
   ```
4. 重跑 dry-run 量时长(应 <10 min):
   ```bash
   ( /usr/bin/flock -w 600 9; set -a; . /etc/policy-pipeline/notify.env; set +a; \
     cd /root/policy-pipeline-src && docker compose -f docker-compose.server.yml run --rm policy-producer \
     python -m scripts.l1_collect.run_incremental --vault-dir /vault/0_raw/policies \
       --l2-queue /state/l2_queue.jsonl --dry-run \
   ) 9>/var/lock/policy-pipeline-producer.lock
   ```
   时长达标 → **回到 `docs/handoffs/2026-06-10-codex-s2-w2w3-night.md` 的 Step 2 继续**(真跑→抽查→push→L2→投影→解 cron)。

**注意**:若执行本手册时旧的串行 dry-run 还在跑(占着 flock 锁),先确认它结束或安全终止(它只读、未写 vault,可中断),再做第 3 步。

---

## 回报格式
diff 摘要 + 两条新测试结果 + 全量 pytest 数字 + 服务器重建后 dry-run 实测时长。报告落 `docs/handoffs/2026-06-10-codex-scan-concurrent-report.md`。
