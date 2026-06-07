"""渠道发现:决策A目标 → Tavily搜 → LLM选真列表页URL → probe验证 → Channel。

治根因:写死URL当天烂(实测国务院403/能源局404)。LLM管"哪个URL是政策列表页"的判断。
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse
import yaml

from .channel_catalog import Channel, ChannelStatus
from .connectivity_probe import probe_url
from .tavily_client import TavilyClient

# 决策A:国家级13核心机构(覆盖加油/充电/电力三业务线)
NATIONAL_TARGETS = [
    {"city": "国家发展和改革委员会", "channel_type": "发改委", "root_domain": "ndrc.gov.cn"},
    {"city": "国家能源局", "channel_type": "能源局", "root_domain": "nea.gov.cn"},
    {"city": "工业和信息化部", "channel_type": "工信部", "root_domain": "miit.gov.cn"},
    {"city": "商务部", "channel_type": "商务部", "root_domain": "mofcom.gov.cn"},
    {"city": "国务院", "channel_type": "国务院", "root_domain": "www.gov.cn"},
    {"city": "财政部", "channel_type": "财政部", "root_domain": "mof.gov.cn"},
    {"city": "住房和城乡建设部", "channel_type": "住建部", "root_domain": "mohurd.gov.cn"},
    {"city": "国家市场监督管理总局", "channel_type": "市监总局", "root_domain": "samr.gov.cn"},
    {"city": "交通运输部", "channel_type": "交通运输部", "root_domain": "mot.gov.cn"},
    {"city": "生态环境部", "channel_type": "生态环境部", "root_domain": "mee.gov.cn"},
    {"city": "国家标准化管理委员会", "channel_type": "标准委", "root_domain": "sac.gov.cn"},
    {"city": "中国人民银行", "channel_type": "央行", "root_domain": "pbc.gov.cn"},
    {"city": "国家税务总局", "channel_type": "税务总局", "root_domain": "chinatax.gov.cn"},
]

for _t in NATIONAL_TARGETS:
    _t.update({"province": "国家", "level": "国家", "city_code": "000000"})

_PROV_CODE = {
    "北京市": "11", "天津市": "12", "河北省": "13", "山西省": "14", "内蒙古自治区": "15",
    "辽宁省": "21", "吉林省": "22", "黑龙江省": "23", "上海市": "31", "江苏省": "32",
    "浙江省": "33", "安徽省": "34", "福建省": "35", "江西省": "36", "山东省": "37",
    "河南省": "41", "湖北省": "42", "湖南省": "43", "广东省": "44", "广西壮族自治区": "45",
    "海南省": "46", "重庆市": "50", "四川省": "51", "贵州省": "52", "云南省": "53",
    "西藏自治区": "54", "陕西省": "61", "甘肃省": "62", "青海省": "63",
    "宁夏回族自治区": "64", "新疆维吾尔自治区": "65",
}

_SYSTEM_PICK = (
    "你在为政策采集系统挑选『政策文件列表页』URL。从候选里选出最像"
    "「持续更新的政策/通知/公告列表栏目」的那个(不是首页、不是单篇文章、不是检索结果页)。"
    '只输出 JSON:{"list_url":"<选中url或空>","confidence":0-1,"reason":"<=20字"}'
)


def province_targets_from_registry(registry_path: Path) -> list:
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or []
    out, seen = [], set()
    for e in raw:
        region = e.get("region") or {}
        if region.get("level") != "省":
            continue
        prov = region.get("name") or ""
        domain = e.get("domain") or ""
        if not prov or prov not in _PROV_CODE or domain in seen:
            continue
        seen.add(domain)
        issuer = e.get("issuer_canonical") or ""
        ctype = "发改委" if ("发展" in issuer or "改革" in issuer) else \
                "能源局" if "能源" in issuer else "政府网"
        out.append({
            "city": prov, "province": prov, "level": "省",
            "city_code": f"{_PROV_CODE[prov]}0000",
            "channel_type": ctype, "root_domain": domain,
        })
    return out


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _same_domain(url: str, root_domain: str) -> bool:
    """候选 URL 是否属于目标机构域名（含子域）。治 Tavily 跨机构串味（miit→ncsti）。"""
    h, rd = _host(url), (root_domain or "").lower()
    return bool(rd) and (h == rd or h.endswith("." + rd))


def _tavily_search(query: str) -> list:
    return TavilyClient().search_urls(query, max_results=5)


def _llm_pick(target_name: str, candidate_urls: list) -> Optional[str]:
    from .common_llm_client import make_judge_client
    llm = make_judge_client()
    if llm is None:
        return None
    return pick_list_url(target_name, candidate_urls, llm)


def pick_list_url(target_name: str, candidate_urls: list,
                  llm_fn: Callable) -> Optional[str]:
    if not candidate_urls:
        return None
    user = f"机构:{target_name}\n候选URL:\n" + "\n".join(candidate_urls)
    try:
        data = json.loads(llm_fn(_SYSTEM_PICK, user))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    url = (data.get("list_url") or "").strip()
    return url if url in candidate_urls else None


def _first_verified(urls: list):
    """按序探测候选,返回第一个 verdict=ok 的 (url, ProbeResult);
    都不 ok 则返回第一个探测结果(作候选兜底);urls 空返回 (None, None)。"""
    fallback = None
    for u in urls:
        pr = probe_url(u)
        if pr.verdict == "ok":
            return u, pr
        if fallback is None:
            fallback = (u, pr)
    return fallback if fallback else (None, None)


def discover_one(target: dict) -> Optional[Channel]:
    """单目标:搜→同域过滤→LLM选→按序探测(LLM选优先,其余同域候选兜底)。
    治 LLM 选了 JS 空壳/坏 URL(如 nea zxwj.htm):probe 不通时自动试其它同域候选,
    用第一个验证的(Tavily 往往也返回了能用的真列表页,只是没被 LLM 选中)。"""
    query = f"{target['city']} 政策文件 通知公告 列表"
    candidates = _tavily_search(query)
    on_domain = [u for u in candidates if _same_domain(u, target["root_domain"])]
    picked = _llm_pick(target["city"], on_domain)
    ordered = ([picked] if picked else []) + [u for u in on_domain if u != picked]
    list_url, pr = _first_verified(ordered)
    if list_url is None:  # 无同域候选 → 首页兜底
        list_url = f"https://{target['root_domain']}/"
        pr = probe_url(list_url)
    status = ChannelStatus.验证 if pr.verdict == "ok" else ChannelStatus.候选
    return Channel(
        city=target["city"], province=target["province"], level=target["level"],
        city_code=target["city_code"], channel_type=target["channel_type"],
        root_domain=target["root_domain"], list_url=list_url,
        source="discovery", status=status,
        last_probed_at=pr.probed_at, probe_result=pr.verdict,
    )
