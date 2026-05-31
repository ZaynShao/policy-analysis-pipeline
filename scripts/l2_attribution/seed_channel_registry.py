"""从 渠道目录.md + refdata 自动派生 channel_registry 草稿,余下入 needs_manual。
派生纯规则:① 部委域名命中 MINISTRY;② 渠道名称含'XX省'->省级;③ 含'XX市'->市级(查 CITY_PROVINCE 定省级码)。
定不了的(媒体/未知市/无渠道名)-> None -> needs_manual。"""
from __future__ import annotations
import re
import json
from pathlib import Path
import yaml
from scripts.l2_attribution.refdata import PROVINCE, MINISTRY, CITY_PROVINCE
from scripts.l2_attribution.channel_registry import host_of
from scripts.l1_audit.corpus import load_policies

_ROW_RE = re.compile(r"^\|\s*([a-z0-9.\-]+\.gov\.cn|[a-z0-9.\-]+\.cn)\s*\|\s*([^|]+?)\s*\|", re.M)
_PROV_RE = re.compile(r"(北京市|天津市|上海市|重庆市|河北省|山西省|内蒙古自治区|辽宁省|吉林省|黑龙江省|江苏省|浙江省|安徽省|福建省|江西省|山东省|河南省|湖北省|湖南省|广东省|广西壮族自治区|海南省|四川省|贵州省|云南省|西藏自治区|陕西省|甘肃省|青海省|宁夏回族自治区|新疆维吾尔自治区)")
_CITY_RE = re.compile(r"([一-龥]{2,8}?市)")


def parse_channel_md(text: str) -> list:
    """渠道目录.md markdown 表 -> [(domain, 渠道名称)]。跳过表头行(渠道名称=='渠道名称')。"""
    out = []
    for dom, name in _ROW_RE.findall(text):
        name = name.strip()
        if name in ("渠道名称", "渠道标识") or not name:
            continue
        out.append((dom, name))
    return out


def _municipality(prov_name):
    return prov_name in ("北京市", "天津市", "上海市", "重庆市")


def derive_entry(domain: str, channel_name: str):
    """规则派生一条 entry dict;定不了返回 None。"""
    if domain in MINISTRY:
        m = MINISTRY[domain]
        return {"domain": domain, "issuer_short": m["issuer_short"],
                "issuer_canonical": m["issuer_canonical"], "region": dict(m["region"])}
    name = channel_name or ""
    # 省级(含直辖市作为省级行政区)
    pm = _PROV_RE.search(name)
    cm = _CITY_RE.search(name)
    # 直辖市:渠道名"上海市..."既是省级码也是市级行政区
    if pm and _municipality(pm.group(1)):
        p = PROVINCE[pm.group(1)]
        return {"domain": domain, "issuer_short": p["issuer_short"],
                "issuer_canonical": name,
                "region": {"level": "市", "code": p["code2"] + "0000", "name": pm.group(1)}}
    # 普通市级:渠道名含"XX市" 且能查到所属省
    if cm and cm.group(1) in CITY_PROVINCE:
        prov = CITY_PROVINCE[cm.group(1)]
        p = PROVINCE[prov]
        return {"domain": domain, "issuer_short": p["issuer_short"],
                "issuer_canonical": name,
                # 市级 adcode 暂用省级回退 + needs_city_code 标记(spec:查不到市码→省级码+标记)
                "region": {"level": "市", "code": p["code2"] + "0000",
                           "name": cm.group(1), "needs_city_code": True}}
    # 省级直属(渠道名含"XX省")
    if pm and pm.group(1) in PROVINCE:
        p = PROVINCE[pm.group(1)]
        return {"domain": domain, "issuer_short": p["issuer_short"],
                "issuer_canonical": name,
                "region": {"level": "省", "code": p["code2"] + "0000", "name": pm.group(1)}}
    return None


def seed(channel_md_path: str, policies_dir: str, out_yaml: str, needs_manual_path: str):
    md = Path(channel_md_path).read_text(encoding="utf-8")
    md_pairs = dict(parse_channel_md(md))
    # 语料里出现的全部 gov 域名
    domains = {}
    for rec in load_policies(policies_dir):
        h = host_of(rec.url)
        if h.endswith(".gov.cn"):
            domains.setdefault(h, rec.path)
    entries, needs_manual = [], []
    for dom, sample_path in sorted(domains.items()):
        e = derive_entry(dom, md_pairs.get(dom, ""))
        if e:
            entries.append(e)
        else:
            needs_manual.append({"domain": dom, "sample_file": Path(sample_path).name,
                                 "channel_name_hint": md_pairs.get(dom, "")})
    Path(out_yaml).write_text(
        yaml.dump(entries, allow_unicode=True, sort_keys=False), encoding="utf-8")
    Path(needs_manual_path).write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in needs_manual), encoding="utf-8")
    return len(entries), len(needs_manual)


if __name__ == "__main__":
    import sys
    vault = sys.argv[1] if len(sys.argv) > 1 else \
        str(Path.home() / "Documents" / "Zayn Main" / "政策分析")
    n_ok, n_manual = seed(
        f"{vault}/00 背景资料/渠道目录.md",
        f"{vault}/0_raw/policies",
        f"{vault}/_meta/channel_registry.yaml",
        "state/source_ready/channel_registry_needs_manual.jsonl",
    )
    print(f"自动派生 {n_ok} 域名;needs_manual {n_manual} 待 curate")
