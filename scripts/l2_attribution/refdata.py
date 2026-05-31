"""参考数据:省级码表(GB/T 2260)+ 部委域名表 + 市→省表。
全是稳定标准数据 / 判断即数据;不规则项进表,不进代码。"""
from __future__ import annotations

# 34 省级行政区:名称 -> {issuer_short(id前缀), code2(省级码前两位)}
# issuer_short 沿用 ① 既定方案:直辖市码=市码;四川=SC;国务院=GWY(不在此表,见 MINISTRY)
PROVINCE = {
    "北京市": {"issuer_short": "BJ", "code2": "11"},
    "天津市": {"issuer_short": "TJ", "code2": "12"},
    "河北省": {"issuer_short": "HE", "code2": "13"},
    "山西省": {"issuer_short": "SX", "code2": "14"},
    "内蒙古自治区": {"issuer_short": "NM", "code2": "15"},
    "辽宁省": {"issuer_short": "LN", "code2": "21"},
    "吉林省": {"issuer_short": "JL", "code2": "22"},
    "黑龙江省": {"issuer_short": "HL", "code2": "23"},
    "上海市": {"issuer_short": "SH", "code2": "31"},
    "江苏省": {"issuer_short": "JS", "code2": "32"},
    "浙江省": {"issuer_short": "ZJ", "code2": "33"},
    "安徽省": {"issuer_short": "AH", "code2": "34"},
    "福建省": {"issuer_short": "FJ", "code2": "35"},
    "江西省": {"issuer_short": "JX", "code2": "36"},
    "山东省": {"issuer_short": "SD", "code2": "37"},
    "河南省": {"issuer_short": "HA", "code2": "41"},
    "湖北省": {"issuer_short": "HB", "code2": "42"},
    "湖南省": {"issuer_short": "HN", "code2": "43"},
    "广东省": {"issuer_short": "GD", "code2": "44"},
    "广西壮族自治区": {"issuer_short": "GX", "code2": "45"},
    "海南省": {"issuer_short": "HI", "code2": "46"},
    "重庆市": {"issuer_short": "CQ", "code2": "50"},
    "四川省": {"issuer_short": "SC", "code2": "51"},
    "贵州省": {"issuer_short": "GZ", "code2": "52"},
    "云南省": {"issuer_short": "YN", "code2": "53"},
    "西藏自治区": {"issuer_short": "XZ", "code2": "54"},
    "陕西省": {"issuer_short": "SN", "code2": "61"},
    "甘肃省": {"issuer_short": "GS", "code2": "62"},
    "青海省": {"issuer_short": "QH", "code2": "63"},
    "宁夏回族自治区": {"issuer_short": "NX", "code2": "64"},
    "新疆维吾尔自治区": {"issuer_short": "XJ", "code2": "65"},
    "香港特别行政区": {"issuer_short": "HK", "code2": "81"},
    "澳门特别行政区": {"issuer_short": "MO", "code2": "82"},
    "台湾省": {"issuer_short": "TW", "code2": "71"},
}

_NAT = {"level": "国家", "code": "000000", "name": "全国"}

# 部委 / 中央域名 -> {issuer_short, issuer_canonical, region}
# 种子来自 渠道目录.md 中央表;新部委由 Task 4 curate 补
MINISTRY = {
    "www.gov.cn":        {"issuer_short": "GWY", "issuer_canonical": "国务院", "region": _NAT},
    "www.ndrc.gov.cn":   {"issuer_short": "NDRC", "issuer_canonical": "国家发展和改革委员会", "region": _NAT},
    "zfxxgk.ndrc.gov.cn":{"issuer_short": "NDRC", "issuer_canonical": "国家发展和改革委员会", "region": _NAT},
    "www.nea.gov.cn":    {"issuer_short": "NEA", "issuer_canonical": "国家能源局", "region": _NAT},
    "zfxxgk.nea.gov.cn": {"issuer_short": "NEA", "issuer_canonical": "国家能源局", "region": _NAT},
    "www.miit.gov.cn":   {"issuer_short": "MIIT", "issuer_canonical": "工业和信息化部", "region": _NAT},
    "www.mof.gov.cn":    {"issuer_short": "MOF", "issuer_canonical": "财政部", "region": _NAT},
    "www.mee.gov.cn":    {"issuer_short": "MEE", "issuer_canonical": "生态环境部", "region": _NAT},
    "www.mohurd.gov.cn": {"issuer_short": "MOHURD", "issuer_canonical": "住房和城乡建设部", "region": _NAT},
    "www.mofcom.gov.cn": {"issuer_short": "MOFCOM", "issuer_canonical": "商务部", "region": _NAT},
    "www.sasac.gov.cn":  {"issuer_short": "SASAC", "issuer_canonical": "国务院国资委", "region": _NAT},
    "xxgk.mot.gov.cn":   {"issuer_short": "MOT", "issuer_canonical": "交通运输部", "region": _NAT},
    "m.12371.gov.cn":    {"issuer_short": "CPC", "issuer_canonical": "共产党员网", "region": _NAT},
    "std.samr.gov.cn":   {"issuer_short": "SAMR", "issuer_canonical": "国家市场监督管理总局", "region": _NAT},
}

# 市 -> 省(语料破损集出现的市;Task 4 curate 补全缺失市)
CITY_PROVINCE = {
    "济南市": "山东省", "苏州市": "江苏省", "广州市": "广东省", "深圳市": "广东省",
    "哈尔滨市": "黑龙江省", "银川市": "宁夏回族自治区", "吕梁市": "山西省",
    # … 执行时按语料补齐(Task 3 的 needs_manual 会列出缺的市)
}
