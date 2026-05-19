"""生成 P0 ~50 城的渠道候选 jsonl → 合并入 channel_catalog.yaml。

策略调整说明(与原 plan 偏差):
  - 原 plan 计划 ~330 全市 + LLM 补全 root_domain。本次 sprint 收窄到 P0 ~50 城,
    直接用 "fgw.<pinyin>.gov.cn" / "<pinyin>fgw.gov.cn" 等模板生成候选;
    P1 / P2 留 T9.1 时扩。
  - LESSONS B6 模糊匹配先校验:模板生成的候选标 source=template_generated,
    必经 T1.4 connectivity_probe gate 才能进 status=验证。

P0 50 城及拼音/国标码硬编码在本脚本(在 T2.1 city_priority 模块定义业务规则之前
就需要城清单,所以本脚本自带一份。两边应保持一致)。

模板(每 channel_type 试多个候选,联通测试 gate 后留下成立的):
  发改委:fgw.<pinyin>.gov.cn, <pinyin>fgw.gov.cn, <pinyin>drc.gov.cn
  能源局:nyj.<pinyin>.gov.cn, <pinyin>nyj.gov.cn
  政府网:www.<pinyin>.gov.cn, <pinyin>.gov.cn
"""
from __future__ import annotations
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.l1_collect.channel_catalog import (
    Channel, ChannelStatus, load_catalog, save_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "state" / "T1_channels" / "channel_catalog.yaml"
VAULT_CATALOG_MD = Path.home() / "Documents" / "Zayn Main" / "政策分析" / "00 背景资料" / "渠道目录.md"
CST = timezone(timedelta(hours=8))

# (city, province, city_code, pinyin_alias_list — 第一个用于 URL 模板,其它作 fallback)
P0_CITIES = [
    # 一线
    ("北京市", "北京市", "110100", ["beijing", "bj"]),
    ("上海市", "上海市", "310100", ["sh", "shanghai"]),
    ("广州市", "广东省", "440100", ["gz", "guangzhou"]),
    ("深圳市", "广东省", "440300", ["sz", "shenzhen"]),
    # 直辖市 / 新一线
    ("天津市", "天津市", "120100", ["tj", "tianjin"]),
    ("重庆市", "重庆市", "500100", ["cq", "chongqing"]),
    ("成都市", "四川省", "510100", ["chengdu", "cd"]),
    ("杭州市", "浙江省", "330100", ["hangzhou", "hz"]),
    ("武汉市", "湖北省", "420100", ["wuhan", "wh"]),
    ("西安市", "陕西省", "610100", ["xa", "xian"]),
    ("南京市", "江苏省", "320100", ["nj", "nanjing"]),
    ("苏州市", "江苏省", "320500", ["suzhou", "sz"]),
    ("长沙市", "湖南省", "430100", ["changsha", "cs"]),
    ("郑州市", "河南省", "410100", ["zhengzhou", "zz"]),
    ("济南市", "山东省", "370100", ["jinan", "jn"]),
    ("合肥市", "安徽省", "340100", ["hefei", "hf"]),
    ("昆明市", "云南省", "530100", ["kunming", "km"]),
    ("无锡市", "江苏省", "320200", ["wuxi", "wx"]),
    ("宁波市", "浙江省", "330200", ["ningbo", "nb"]),
    ("青岛市", "山东省", "370200", ["qingdao", "qd"]),
    ("厦门市", "福建省", "350200", ["xiamen", "xm"]),
    ("福州市", "福建省", "350100", ["fuzhou", "fz"]),
    ("沈阳市", "辽宁省", "210100", ["shenyang", "sy"]),
    # 加油 top50 增量(去重后)
    ("东莞市", "广东省", "441900", ["dg", "dongguan"]),
    ("佛山市", "广东省", "440600", ["fs", "foshan"]),
    ("嘉兴市", "浙江省", "330400", ["jiaxing", "jx"]),
    ("温州市", "浙江省", "330300", ["wenzhou", "wz"]),
    ("泉州市", "福建省", "350500", ["quanzhou", "qz"]),
    ("南通市", "江苏省", "320600", ["nantong", "nt"]),
    ("烟台市", "山东省", "370600", ["yantai", "yt"]),
    ("潍坊市", "山东省", "370700", ["weifang", "wf"]),
    ("常州市", "江苏省", "320400", ["changzhou", "cz"]),
    ("惠州市", "广东省", "441300", ["huizhou", "hz2"]),
    # 电力业务:省会(去重后) + 计划单列
    ("石家庄市", "河北省", "130100", ["shijiazhuang", "sjz"]),
    ("太原市", "山西省", "140100", ["taiyuan", "ty"]),
    ("呼和浩特市", "内蒙古自治区", "150100", ["huhhot", "hhht"]),
    ("长春市", "吉林省", "220100", ["changchun", "cc"]),
    ("哈尔滨市", "黑龙江省", "230100", ["harbin", "hrb"]),
    ("南昌市", "江西省", "360100", ["nanchang", "nc"]),
    ("贵阳市", "贵州省", "520100", ["guiyang", "gy"]),
    ("拉萨市", "西藏自治区", "540100", ["lasa", "lhasa"]),
    ("兰州市", "甘肃省", "620100", ["lanzhou", "lz"]),
    ("西宁市", "青海省", "630100", ["xining", "xn"]),
    ("银川市", "宁夏回族自治区", "640100", ["yinchuan", "yc"]),
    ("乌鲁木齐市", "新疆维吾尔自治区", "650100", ["wulumuqi", "urumqi"]),
    ("海口市", "海南省", "460100", ["haikou", "hk"]),
    ("南宁市", "广西壮族自治区", "450100", ["nanning", "nn"]),
    ("大连市", "辽宁省", "210200", ["dalian", "dl"]),
]

CHANNEL_TEMPLATES = {
    "发改委": [
        "fgw.{p}.gov.cn",
        "{p}fgw.gov.cn",
        "{p}drc.gov.cn",
        "drc.{p}.gov.cn",
    ],
    "能源局": [
        "nyj.{p}.gov.cn",
        "{p}nyj.gov.cn",
    ],
    "政府网": [
        "www.{p}.gov.cn",
        "{p}.gov.cn",
    ],
}


CHANNEL_TYPE_KEYWORDS = {
    "发改委": ["发展和改革委员会", "发改委", "发改", "drc"],
    "能源局": ["能源局", "能源监管", "能源"],
    "政府网": ["人民政府", "政府门户", "市政府", "政府网", "政府办公厅"],
}


def _load_known_from_vault() -> dict[tuple[str, str], dict]:
    """从 vault 渠道目录.md 抽 (city, channel_type) → root_domain。

    vault 用"上海市发展和改革委员会"全称,所以匹配关键词列表不只是简称。
    """
    if not VAULT_CATALOG_MD.exists():
        return {}
    text = VAULT_CATALOG_MD.read_text(encoding="utf-8")
    out: dict[tuple[str, str], dict] = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*([a-zA-Z0-9.\-]+\.gov\.cn)\s*\|\s*(.+?)\s*\|", line)
        if not m:
            continue
        domain, name = m.group(1), m.group(2).strip()
        ct = None
        for t, kws in CHANNEL_TYPE_KEYWORDS.items():
            if any(kw in name for kw in kws):
                ct = t
                break
        if ct is None:
            continue
        city_m = re.search(r"([一-龥]{2,5}(?:市|自治州))", name)
        if not city_m:
            continue
        city = city_m.group(1)
        # 国家级"国家市场监督管理总局"等不算 city,过滤
        if city.startswith("国家"):
            continue
        out[(city, ct)] = {"root_domain": domain, "name": name}
    return out


def _list_url(domain: str, channel_type: str) -> str:
    """猜测列表页 URL — 大多政府网用 /zwgk/ 或 /zfxxgk/,无统一规律,
    候选 list_url 设空,Step 2 扫描时再用 root domain index 兜底。"""
    return f"https://{domain}/"


def main() -> None:
    now = datetime.now(CST).isoformat(timespec="seconds")
    catalog_old = load_catalog(CATALOG) if CATALOG.exists() else []
    seen = {(c.city, c.channel_type, c.root_domain) for c in catalog_old}
    known_from_vault = _load_known_from_vault()
    print(f"vault catalog known: {len(known_from_vault)} (city, channel_type) entries")

    added = 0
    new_channels: list[Channel] = []
    for city, province, city_code, pinyins in P0_CITIES:
        for ct in CHANNEL_TEMPLATES:
            # 1) vault canonical 进 catalog(若有),但**不阻塞** template 候选共存
            #    (vault 抽取可能因 markdown 格式而错绑,联通测试 gate 选优)
            key = (city, ct)
            if key in known_from_vault:
                domain = known_from_vault[key]["root_domain"]
                if (city, ct, domain) not in seen:
                    new_channels.append(Channel(
                        city=city, province=province, level="市", city_code=city_code,
                        channel_type=ct, root_domain=domain,
                        list_url=f"https://{domain}/",
                        source="vault_catalog", status=ChannelStatus.候选,
                        last_probed_at=None, probe_result=None, notes="from vault catalog",
                    ))
                    seen.add((city, ct, domain))
                    added += 1
            # 2) 模板生成多候选(无论 vault 有无)
            for pin in pinyins:
                for tpl in CHANNEL_TEMPLATES[ct]:
                    domain = tpl.format(p=pin)
                    if (city, ct, domain) in seen:
                        continue
                    new_channels.append(Channel(
                        city=city, province=province, level="市", city_code=city_code,
                        channel_type=ct, root_domain=domain,
                        list_url=f"https://{domain}/",
                        source="template_generated", status=ChannelStatus.候选,
                        last_probed_at=None, probe_result=None,
                        notes=f"template={tpl} pinyin={pin}",
                    ))
                    seen.add((city, ct, domain))
                    added += 1
    catalog = catalog_old + new_channels
    save_catalog(catalog, CATALOG)
    print(f"P0 cities: {len(P0_CITIES)}")
    print(f"channels added: {added}")
    print(f"catalog total: {len(catalog)}")
    print(f"saved to {CATALOG}")


if __name__ == "__main__":
    main()
