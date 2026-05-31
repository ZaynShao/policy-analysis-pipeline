import yaml
from pathlib import Path
from scripts.l2_attribution.models import ResolvedIdentity
from scripts.l2_attribution.apply_identity import apply_identity

RAW = """---
id: P_2015_GO_af076ca3
aliases:
- P_2015_GO_af076ca3
title: 济南市人民政府办公厅关于加强成品油监管的通知
issuer:
- 政府门户.www.jinan.gov.cn
date: '2015-01-01'
region:
  level: 国家
  code: '000000'
  name: 未知
type: policy
provenance:
  url: https://www.jinan.gov.cn/x.html
  fetched_at: '2026-05-08'
---

# 标题

## 政策原文
正文……
"""


def _ri():
    ri = ResolvedIdentity(pid="P_2015_GO_af076ca3")
    ri.set_field("region", {"level": "市", "code": "370100", "name": "济南市"},
                 method="domain_lookup", confidence=0.99, from_val="国家/000000/未知")
    ri.set_field("issuer", ["济南市人民政府办公厅"], method="title_extract",
                 confidence=0.95, from_val="政府门户.www.jinan.gov.cn")
    ri.set_field("date", "2016-03-17", method="body_chinese_date",
                 confidence=0.92, from_val="2015-01-01")
    ri.set_field("id", "P_2016_SD_af076ca3", method="id_recompute_from_metadata",
                 confidence=0.99, from_val="P_2015_GO_af076ca3")
    return ri


def test_apply_writes_all_fields_and_nested_audit(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text(RAW, encoding="utf-8")
    written = apply_identity(str(f), _ri(), fixed_at="2026-05-31T10:00:00+08:00")
    text = f.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---")[1])

    assert fm["id"] == "P_2016_SD_af076ca3"
    assert "P_2015_GO_af076ca3" in fm["aliases"]      # 旧 id 保留
    assert "P_2016_SD_af076ca3" in fm["aliases"]      # 新 id 也在
    assert fm["issuer"] == ["济南市人民政府办公厅"]
    assert fm["region"]["code"] == "370100"
    assert fm["date"] == "2016-03-17"
    # 审计字段嵌套在 provenance
    assert fm["provenance"]["id_fixed_method"] == "id_recompute_from_metadata"
    assert fm["provenance"]["region_fixed_from"] == "国家/000000/未知"
    assert fm["provenance"]["date_fixed_method"] == "body_chinese_date"
    # body 不动
    assert "## 政策原文" in text
    # 文件名不变
    assert f.name == "doc.md"
    assert set(written) >= {"id", "issuer", "region", "date"}


def test_apply_noop_when_no_fields(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text(RAW, encoding="utf-8")
    written = apply_identity(str(f), ResolvedIdentity(pid="P_x"),
                             fixed_at="2026-05-31T10:00:00+08:00")
    assert written == []
    assert f.read_text(encoding="utf-8") == RAW   # 完全不动
