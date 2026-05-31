"""参考数据:省级码表(GB/T 2260)+ 部委域名表 + 市→省表。
全是稳定标准数据 / 判断即数据;不规则项进表,不进代码。"""
from __future__ import annotations

# 省级行政区拼音(缩写+全拼) -> 省名(键入 PROVINCE)
PROVINCE_PINYIN = {
    "bj":"北京市","beijing":"北京市", "tj":"天津市","tianjin":"天津市",
    "he":"河北省","hebei":"河北省", "sx":"山西省","shanxi":"山西省",
    "nm":"内蒙古自治区","neimenggu":"内蒙古自治区",
    "ln":"辽宁省","liaoning":"辽宁省", "jl":"吉林省","jilin":"吉林省",
    "hl":"黑龙江省","heilongjiang":"黑龙江省",
    "sh":"上海市","shanghai":"上海市", "js":"江苏省","jiangsu":"江苏省",
    "zj":"浙江省","zhejiang":"浙江省", "ah":"安徽省","anhui":"安徽省",
    "fj":"福建省","fujian":"福建省", "jx":"江西省","jiangxi":"江西省",
    "sd":"山东省","shandong":"山东省", "ha":"河南省","henan":"河南省",
    "hb":"湖北省","hubei":"湖北省", "hn":"湖南省","hunan":"湖南省",
    "gd":"广东省","guangdong":"广东省", "gx":"广西壮族自治区","guangxi":"广西壮族自治区",
    "hi":"海南省","hainan":"海南省", "cq":"重庆市","chongqing":"重庆市",
    "sc":"四川省","sichuan":"四川省", "gz":"贵州省","guizhou":"贵州省",
    "yn":"云南省","yunnan":"云南省", "xz":"西藏自治区","xizang":"西藏自治区",
    "sn":"陕西省","shaanxi":"陕西省", "gs":"甘肃省","gansu":"甘肃省",
    "qh":"青海省","qinghai":"青海省", "nx":"宁夏回族自治区","ningxia":"宁夏回族自治区",
    "xj":"新疆维吾尔自治区","xinjiang":"新疆维吾尔自治区",
}

# 部委 / 中央机构域名末段 -> (issuer_short, canonical)
MINISTRY_LABEL = {
    "www":("GWY","国务院"), "gov":("GWY","国务院"),
    "ndrc":("NDRC","国家发展和改革委员会"), "nea":("NEA","国家能源局"),
    "miit":("MIIT","工业和信息化部"), "mof":("MOF","财政部"),
    "mee":("MEE","生态环境部"), "mohurd":("MOHURD","住房和城乡建设部"),
    "mofcom":("MOFCOM","商务部"), "sasac":("SASAC","国务院国资委"),
    "mot":("MOT","交通运输部"), "samr":("SAMR","国家市场监督管理总局"),
    "chinatax":("STA","国家税务总局"), "12371":("CPC","共产党员网"),
    "moa":("MOA","农业农村部"), "mct":("MCT","文化和旅游部"),
    "nhc":("NHC","国家卫生健康委员会"), "nsfc":("NSFC","国家自然科学基金委员会"),
    "ncsti":("NCSTI","国家科技信息研究所"), "forestry":("NFA","国家林业和草原局"),
}

# 城市拼音 -> 中文市名
CITY_PINYIN = {
    # 华北
    "baotou":"包头市",        # 内蒙古 — 包头市人民政府
    "ordos":"鄂尔多斯市",    # 内蒙古 — 鄂府发〔2025〕42号
    "chifeng":"赤峰市",      # 内蒙古 — 赤峰市交通运输局
    "tangshan":"唐山市",      # 河北省 — 唐山建成电动重卡虚拟电厂
    "chengde":"承德市",      # 河北省 — 承德市商务局
    "hd":"邯郸市",           # 河北省 — 邯郸市人民政府(邯政字)
    "lvliang":"吕梁市",      # 山西省 — 吕梁市人民政府
    # 东北
    "changchun":"长春市",    # 吉林省 — drc.changchun.gov.cn
    # 华东
    "nanjing":"南京市",      # 江苏省 — 南京市人民政府
    "suzhou":"苏州市",        # 江苏省 — 苏州工业园区
    "changzhou":"常州市",    # 江苏省 — 常州市发展改革
    "hangzhou":"杭州市",      # 浙江省 — 杭州市人民政府
    "pudong":"浦东新区",      # 上海市 — 上海市商务委
    "songjiang":"松江区",    # 上海市 — 松江区发展和改革委员会
    # 华中
    "wuhan":"武汉市",        # 湖北省 — 武汉市人民政府
    "zhengzhou":"郑州市",    # 河南省 — 郑州市电动汽车充电
    "jinan":"济南市",        # 山东省 — 济南市人民政府
    "jining":"济宁市",        # 山东省 — 济宁市人民政府
    "luan":"六安市",          # 安徽省 — 六安市商务局
    # 华南
    "sz":"深圳市",            # 广东省 — 深圳市人民政府
    "liuzhou":"柳州市",      # 广西壮族自治区 — 柳州市发展和改革委员会
    "shanwei":"汕尾市",      # 广东省 — 汕尾市商务局
    "zs":"中山市",            # 广东省 — 中山市发展和改革局
    # 西南
    "yinchuan":"银川市",      # 宁夏回族自治区 — 银川市人民政府
    "chaoyang":"朝阳市",      # 辽宁省 — 朝阳市商务局(辽宁朝阳,非北京朝阳区)
}


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
    # 城市拼音解析补充(Task 4)
    "包头市": "内蒙古自治区",
    "鄂尔多斯市": "内蒙古自治区",
    "赤峰市": "内蒙古自治区",
    "唐山市": "河北省",
    "承德市": "河北省",
    "邯郸市": "河北省",
    "长春市": "吉林省",
    "南京市": "江苏省",
    "常州市": "江苏省",
    "杭州市": "浙江省",
    "浦东新区": "上海市",
    "松江区": "上海市",
    "武汉市": "湖北省",
    "郑州市": "河南省",
    "济宁市": "山东省",
    "六安市": "安徽省",
    "柳州市": "广西壮族自治区",
    "汕尾市": "广东省",
    "中山市": "广东省",
    "朝阳市": "辽宁省",
}
