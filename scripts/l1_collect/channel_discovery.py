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
from .city_priority import MUNICIPALITIES, BUSINESS_RULES
from .connectivity_probe import probe_url
from .news_filter import GOV_DOMAIN_SUFFIXES
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

_CODE_TO_PROV = {v: k for k, v in _PROV_CODE.items()}

# 加油线 10 重点市国标码;须与 city_priority.BUSINESS_RULES["加油"][0] 同步
_CITY_CODE = {
    "东莞市": "441900", "佛山市": "440600", "嘉兴市": "330400", "温州市": "330300",
    "泉州市": "350500", "南通市": "320600", "烟台市": "370600", "潍坊市": "370700",
    "常州市": "320400", "惠州市": "441300",
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


_INST_DOMAIN_MARKERS = {
    "商务": ("swt", "sww", "swj", "commerce", "mofcom"),
    "市监": ("scjg", "scjgj", "amr", "samr", "scjgdj"),
}

# 省 → gov 域拼音段(缩写+全拼);host 按 "." 分段做相等匹配,避免子串误命中
_PROV_TOKENS = {
    "北京市": ("bj", "beijing"), "天津市": ("tj", "tianjin"), "河北省": ("he", "hebei"),
    "山西省": ("sx", "shanxi"), "内蒙古自治区": ("nm", "nmg", "neimenggu"),
    "辽宁省": ("ln", "liaoning"), "吉林省": ("jl", "jilin"), "黑龙江省": ("hlj", "heilongjiang"),
    "上海市": ("sh", "shanghai"), "江苏省": ("js", "jiangsu"), "浙江省": ("zj", "zhejiang"),
    "安徽省": ("ah", "anhui"), "福建省": ("fj", "fujian"), "江西省": ("jx", "jiangxi"),
    "山东省": ("sd", "shandong"), "河南省": ("ha", "henan"), "湖北省": ("hb", "hubei"),
    "湖南省": ("hn", "hunan"), "广东省": ("gd", "guangdong"), "广西壮族自治区": ("gx", "guangxi"),
    "海南省": ("hi", "hainan"), "重庆市": ("cq", "chongqing"), "四川省": ("sc", "sichuan"),
    "贵州省": ("gz", "guizhou"), "云南省": ("yn", "yunnan"), "西藏自治区": ("xz", "xizang", "tibet"),
    "陕西省": ("shaanxi", "sn"), "甘肃省": ("gs", "gansu"), "青海省": ("qh", "qinghai"),
    "宁夏回族自治区": ("nx", "ningxia"), "新疆维吾尔自治区": ("xj", "xinjiang"),
}
# 加油线 10 重点市国标码 → gov 域拼音段(缩写+全拼)
_CITY_TOKENS = {
    "441900": ("dg", "dongguan"), "440600": ("fs", "foshan"), "330400": ("jx", "jiaxing"),
    "330300": ("wz", "wenzhou"), "350500": ("qz", "quanzhou"), "320600": ("nt", "nantong"),
    "370600": ("yt", "yantai"), "370700": ("wf", "weifang"), "320400": ("cz", "changzhou"),
    "441300": ("hz", "huizhou"),
}


def _area_match(domain: str, target: dict) -> bool:
    """host 按 '.' 分段,任一段 == 期望省/市拼音 token 即命中。"""
    segs = (domain or "").lower().split(".")
    tokens = set(_PROV_TOKENS.get(target.get("province", ""), ()))
    if target.get("level") == "市":
        tokens |= set(_CITY_TOKENS.get(target.get("city_code", ""), ()))
    return any(t in segs for t in tokens)


def _is_gov_host(url: str) -> bool:
    return any(_host(url).endswith(s) for s in GOV_DOMAIN_SUFFIXES)


def _institution_match(domain: str, target: dict) -> bool:
    """域名无关发现路径核验:host 行政区段 或 机构 marker 命中即过。
    非商务/市监 channel_type 返回 True(发改委/能源等不受影响)。"""
    ctype = target.get("channel_type", "")
    markers = _INST_DOMAIN_MARKERS.get(ctype)
    if markers is None:
        return True
    h = (domain or "").lower()
    marker_ok = any(m in h for m in markers)
    return _area_match(domain, target) or marker_ok


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


def _commerce_name(prov: str) -> str:
    return f"{prov}商务局" if prov in MUNICIPALITIES else f"{prov}商务厅"


def _warmstart_domains(registry_path) -> dict:
    """registry 里 issuer 含'商务'或'市场监督' → {显示名: domain},用于暖启动。"""
    if registry_path is None or not Path(registry_path).exists():
        return {}
    raw = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or []
    out = {}
    for e in raw:
        iss = e.get("issuer_canonical") or ""
        dom = e.get("domain") or ""
        if ("商务" in iss or "市场监督" in iss) and dom:
            out[iss] = dom
    return out


def commerce_market_targets(registry_path: Optional[Path] = None) -> list:
    """商务厅(31省+加油线重点市)+ 市监局(31省)目标。root_domain 多为 None(待发现)。"""
    warm = _warmstart_domains(registry_path)
    oil_cities = sorted(BUSINESS_RULES["加油"][0]["cities"])  # 10 重点市
    out = []
    for prov, code in _PROV_CODE.items():
        cname = _commerce_name(prov)
        out.append({"city": cname, "province": prov, "level": "省",
                    "city_code": f"{code}0000", "channel_type": "商务",
                    "root_domain": warm.get(cname)})
        out.append({"city": f"{prov}市场监督管理局", "province": prov, "level": "省",
                    "city_code": f"{code}0000", "channel_type": "市监",
                    "root_domain": warm.get(f"{prov}市场监督管理局")})
    # 商务重点市(加油线)
    for city in oil_cities:
        city_code = _CITY_CODE.get(city, "")
        out.append({"city": f"{city}商务局",
                    "province": _CODE_TO_PROV.get(city_code[:2], ""),
                    "level": "市",
                    "city_code": city_code, "channel_type": "商务",
                    "root_domain": warm.get(f"{city}商务局")})
    return out


def discover_one(target: dict) -> Optional[Channel]:
    """单目标:搜→域名过滤→LLM选→按序探测→反推域名→机构核验→Channel。

    已知域名(known):同域过滤;未知域名(None):gov.cn 过滤 + 反推域名 + 机构名核验。
    治 LLM 选了 JS 空壳/坏 URL:probe 不通时自动试其它候选,用第一个验证的。
    """
    query = f"{target['city']} 政策文件 通知公告 列表"
    candidates = _tavily_search(query)
    known = target.get("root_domain")
    if known:
        on_domain = [u for u in candidates if _same_domain(u, known)]
    else:
        on_domain = [u for u in candidates if _is_gov_host(u)]   # 域名未知→gov 过滤
    picked = _llm_pick(target["city"], on_domain)
    ordered = ([picked] if picked else []) + [u for u in on_domain if u != picked]
    list_url, pr = _first_verified(ordered)
    if list_url is None:  # 无候选 → 首页兜底(仅 known-domain 路径有意义)
        list_url = f"https://{known}/" if known else (
            f"https://{_host(picked)}/" if picked else "")
        pr = probe_url(list_url) if list_url else None
    resolved = known or (_host(list_url) if list_url else "")
    inst_ok = True if known else _institution_match(resolved, target)
    verdict_ok = bool(pr) and pr.verdict == "ok"
    status = ChannelStatus.验证 if (verdict_ok and inst_ok) else ChannelStatus.候选
    return Channel(
        city=target["city"], province=target["province"], level=target["level"],
        city_code=target["city_code"], channel_type=target["channel_type"],
        root_domain=resolved, list_url=list_url, source="discovery", status=status,
        last_probed_at=(pr.probed_at if pr else None),
        probe_result=(pr.verdict if pr else None),
    )
