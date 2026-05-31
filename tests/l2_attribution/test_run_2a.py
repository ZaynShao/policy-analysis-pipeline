import json
from pathlib import Path
from scripts.l2_attribution.run_2a import plan

REG_YAML = """- domain: www.jinan.gov.cn
  issuer_short: SD
  issuer_canonical: 济南市人民政府
  region: {level: 市, code: '370100', name: 济南市}
"""
DOC = """---
id: P_2015_GO_af076ca3
aliases: [P_2015_GO_af076ca3]
title: 济南市人民政府办公厅关于加强成品油监管的通知
issuer: [政府门户.www.jinan.gov.cn]
date: '2015-01-01'
region: {level: 国家, code: '000000', name: 未知}
type: policy
provenance: {url: 'https://www.jinan.gov.cn/x.html'}
---

## 政策原文
正文……

济南市人民政府办公厅

2016年3月17日
"""


def _setup(tmp_path):
    pol = tmp_path / "0_raw" / "policies"; pol.mkdir(parents=True)
    (pol / "doc.md").write_text(DOC, encoding="utf-8")
    reg = tmp_path / "channel_registry.yaml"; reg.write_text(REG_YAML, encoding="utf-8")
    led = tmp_path / "ledger.jsonl"
    led.write_text('{"pid":"P_2015_GO_af076ca3","suggested_issuer_short":"SD","true_region":"济南市"}\n',
                   encoding="utf-8")
    return str(pol), str(reg), str(led)


def test_plan_clean_doc_goes_to_apply(tmp_path):
    pol, reg, led = _setup(tmp_path)
    to_apply, queue = plan(pol, reg, led)
    assert len(to_apply) == 1
    assert to_apply[0].fields["id"].value == "P_2016_SD_af076ca3"
    assert queue == []


def test_plan_ledger_disagree_demotes_to_queue(tmp_path):
    pol, reg, led = _setup(tmp_path)
    Path(led).write_text('{"pid":"P_2015_GO_af076ca3","suggested_issuer_short":"NDRC","true_region":"national"}\n',
                         encoding="utf-8")
    to_apply, queue = plan(pol, reg, led)
    assert to_apply == []
    assert len(queue) == 1
    assert any(c.field == "_all" for c in queue[0].conflicts)
