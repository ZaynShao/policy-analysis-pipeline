// ②-B Task13 gold 标注工作流(一次性)。
// 50 篇政策 × 3 Claude 模型(opus/sonnet/haiku)独立标 theme+6维分,脚本算一致性。
// 路径写死(避免 args 不传问题)。用法:在新 session 里 Workflow({scriptPath: 本文件绝对路径})。
export const meta = {
  name: 'node2b-gold-label',
  description: '50篇政策×3 Claude模型(opus/sonnet/haiku)独立标 gold(theme+6维分),算一致性,分歧挑出交用户裁',
  phases: [{ title: 'Label', detail: '每篇 3 模型独立标注 + 算一致性' }],
}

const SAMPLE_PATH = '/Users/shaoziyuan/dev/政策分析-pipeline/state/node2b/golden/sample_pids.json'
const REGISTRY_PATH = '/Users/shaoziyuan/Documents/Zayn Main/政策分析/_meta/themes_registry.yaml'
const SCORING_PATH = '/Users/shaoziyuan/Documents/Zayn Main/政策分析/_meta/framework/scoring.yaml'
const FRAMEWORK_PATH = '/Users/shaoziyuan/Documents/Zayn Main/政策分析/_meta/framework/decision_framework.yaml'

const SAMPLE_SCHEMA = {
  type: 'object',
  properties: {
    policies: { type: 'array', items: { type: 'object', properties: {
      pid: { type: 'string' }, title: { type: 'string' },
      path: { type: 'string' }, level: { type: 'string' },
    }, required: ['pid', 'path'] } },
  }, required: ['policies'],
}

const LABEL_SCHEMA = {
  type: 'object',
  properties: {
    themes: { type: 'array', items: { type: 'string' } },
    primary_theme: { type: 'string' },
    scores: { type: 'object', properties: {
      D1: { type: 'integer' }, D2: { type: 'integer' }, D3: { type: 'integer' },
      D4: { type: 'integer' }, D5: { type: 'integer' }, D6: { type: 'integer' },
    }, required: ['D1', 'D2', 'D3', 'D4', 'D5', 'D6'] },
    impact: { type: 'object', properties: {
      fuel: { type: 'string' }, charging: { type: 'string' }, power: { type: 'string' },
    } },
    rationale: { type: 'string' },
  }, required: ['themes', 'primary_theme', 'scores', 'rationale'],
}

function buildPrompt(pol) {
  return `你是为滴滴能源建立「标准答案(ground truth)」的资深政策分析师。务必审慎精确——你的标注是校准其他模型的金标准,不是快速生产。

先用 Read 工具读以下文件,吃透规则与政策原文:
1. 合法主题表(theme id 只能从中选):${REGISTRY_PATH}
2. 六维打分体系(D1-D6 定义/范围/重要性公式):${SCORING_PATH}
3. 决策框架(三业务=加油/充电/电力;乡村并入充电,非独立类目):${FRAMEWORK_PATH}
4. 待标政策全文:${pol.path}

标注要求:
- themes:挂上所有「语义」真正命中的主题(从主题表 id 选,可多个;出现关键词≠必挂,以语义为准);零相关给空数组 []。
- primary_theme:themes 里最核心的 1 个(themes 空则给 "")。
- scores:严格按六维定义给 D1-D6 整数分(0-5)。
- impact:仅当 importance(=round(0.4*D1+0.4*D2+0.2*D3))≥3 或层级为国家/省级时填;fuel/charging/power 各一句(power=储能/VPP/V2G/电力交易);否则三键都给 ""。
- rationale:一句话说明挂这些主题与关键打分的理由。

该政策层级提示:${pol.level || '(未知)'}。只按结构化 schema 输出,不要额外文字。`
}

function setEq(a, b) {
  const A = new Set(a), B = new Set(b)
  if (A.size !== B.size) return false
  for (const x of A) if (!B.has(x)) return false
  return true
}

function median(nums) {
  const s = [...nums].sort((x, y) => x - y)
  const n = s.length
  if (n === 0) return null
  return n % 2 ? s[(n - 1) / 2] : Math.round((s[n / 2 - 1] + s[n / 2]) / 2)
}

function consensus(pol, labels) {
  const valid = labels.filter(x => x && x.label && x.label.scores)
  const n = valid.length
  const raw = valid.map(x => ({
    model: x.model, themes: x.label.themes || [], primary: x.label.primary_theme || '',
    scores: x.label.scores, impact: x.label.impact || null, rationale: x.label.rationale || '',
  }))
  if (n === 0) {
    return { pid: pol.pid, title: pol.title, level: pol.level, agreement: 'failed', n_labelers: 0, raw, consensus: null }
  }
  const counts = {}
  for (const r of raw) for (const t of r.themes) counts[t] = (counts[t] || 0) + 1
  const need = Math.floor(n / 2) + 1
  const consensusThemes = Object.keys(counts).filter(t => counts[t] >= need).sort()
  const disputedThemes = Object.keys(counts).filter(t => counts[t] > 0 && counts[t] < need).sort()
  const themesUnanimous = raw.every(r => setEq(r.themes, raw[0].themes))
  const pc = {}
  for (const r of raw) pc[r.primary] = (pc[r.primary] || 0) + 1
  const primarySorted = Object.keys(pc).sort((a, b) => pc[b] - pc[a])
  const topPrimary = primarySorted[0] || ''
  const primaryUnanimous = raw.every(r => r.primary === raw[0].primary)
  const primaryMajority = (pc[topPrimary] || 0) >= need
  const dims = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6']
  const med = {}, spread = {}
  for (const d of dims) {
    const vals = raw.map(r => Number(r.scores[d]))
    med[d] = median(vals)
    spread[d] = Math.max(...vals) - Math.min(...vals)
  }
  const maxSpread = Math.max(...dims.map(d => spread[d]))
  const importance = Math.round(0.4 * med.D1 + 0.4 * med.D2 + 0.2 * med.D3)
  let level
  if (themesUnanimous && primaryUnanimous && maxSpread <= 1) level = 'high'
  else if (disputedThemes.length <= 1 && primaryMajority && maxSpread <= 2) level = 'mid'
  else level = 'low'
  return {
    pid: pol.pid, title: pol.title, level: pol.level, agreement: level, n_labelers: n,
    consensus: { themes: consensusThemes, primary_theme: topPrimary, scores: med, importance },
    disputed: { themes: disputedThemes, primary_unanimous: primaryUnanimous, max_score_spread: maxSpread, score_spread: spread },
    raw,
  }
}

const policies = [{"pid": "P_2020_HN_7de5ab8e", "title": "国家能源局有关负责同志就《关于加强新能源汽车与电网融合互动的 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【国家能源局有关负责同志就《关于加强新能源汽车与电网融合互动的 ...】-湖南省发展和改革委员会-7de5ab8e.md", "level": "省"}, {"pid": "P_2024_GD_378cdbce", "title": "深圳市发展和改革委员会关于印发《深圳市支持虚拟电厂加快发展的 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【深圳市发展和改革委员会关于印发《深圳市支持虚拟电厂加快发展的 ...(深发改规〔2024〕4号)】-政府门户.fgw.sz.gov.cn-378cdbce.md", "level": "市"}, {"pid": "P_2024_NDRC_718", "title": "推动车网互动规模化应用试点工作的通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【推动车网互动规模化应用试点工作的通知(发改办能源〔2024〕718号)】-国家发展改革委办公厅 国家能源局 工业和信息化部 市场监管总局-2ed7.md", "level": "国家"}, {"pid": "P_2019_GZ_64193177", "title": "贵州省电网建设专项行动方案", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【贵州省电网建设专项行动方案】-贵州省发展和改革委员会-64193177.md", "level": "省"}, {"pid": "P_2022_GO_6a4cc949", "title": "国务院办公厅转发国家发展改革委国家能源局关于促进新时代新能源高质量发展实施方案的通知 国办函〔2022〕39号-国家能源局网站", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【国务院办公厅转发国家发展改革委国家能源局关于促进新时代新能源高质量发展实施方案的通知 国办函〔2022〕39号-国家能源局网站(国办函〔2022〕39号)】-国家能源局-6a4cc949.md", "level": "国家"}, {"pid": "P_2015_SD_af076ca3", "title": "济南市人民政府办公厅关于进一步加强成品油监管工作的通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【济南市人民政府办公厅关于进一步加强成品油监管工作的通知(鲁政办字〔2015〕194号)】-政府门户.www.jinan.gov.cn-af076ca3.md", "level": "市"}, {"pid": "P_2019_FJ_99e4d508", "title": "省商务厅调整与成品油市场准入改革相关的权责事项清单", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【省商务厅调整与成品油市场准入改革相关的权责事项清单(国办发〔2019〕42号)】-政府门户.swt.fujian.gov.cn-99e4d508.md", "level": "省"}, {"pid": "P_2020_SH_d3a442c8", "title": "上海市经济信息化委关于进一步加强成品油市场管理的紧急通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【上海市经济信息化委关于进一步加强成品油市场管理的紧急通知】-政府门户.www.sheitc.sh.gov.cn-d3a442c8.md", "level": "市"}, {"pid": "P_2024_GD_d62c53cf", "title": "广州市市场监督管理局关于印发广州市以标准提升牵引设备更新和消费品以旧换新行动方案的通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【广州市市场监督管理局关于印发广州市以标准提升牵引设备更新和消费品以旧换新行动方案的通知】-政府门户.scjgj.gz.gov.cn-d62c53cf.md", "level": "市"}, {"pid": "P_2025_BJ_3701c968", "title": "2024年度总目录索引 - 北京市人民政府", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【2024年度总目录索引 - 北京市人民政府】-北京市人民政府-3701c968.md", "level": "省"}, {"pid": "P_1900_SX_caf8e7eb", "title": "国家发展改革委、国务院国资委、中国证监会、全国工商联有关负责同志就《关于完善中国特色现代企业制度的意见》相关情况答记者问-山西省发改委门户网站", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【国家发展改革委、国务院国资委、中国证监会、全国工商联有关负责同志就《关于完善中国特色现代企业制度的意见》相关情况答记者问-山西省发改委门户网站】-山西省发展和改革委员会-.md", "level": "省"}, {"pid": "P_1990_NEA_1162", "title": "加强电网调峰工作若干规定", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【加强电网调峰工作若干规定(能源办〔1990〕1162号)】-国家能源局（原能源部）-c7c5.md", "level": "国家"}, {"pid": "P_2012_BJ_466935e2", "title": "（失效）北京市发展和改革委员会转发国家发展改革委关于提高成品 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【（失效）北京市发展和改革委员会转发国家发展改革委关于提高成品 ...(京发改〔2012〕1370号)】-北京市发展和改革委员会-466935e2.md", "level": "省"}, {"pid": "P_2012_SH_020", "title": "上海市居民生活用电试行阶梯电价实施方案", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【上海市居民生活用电试行阶梯电价实施方案(沪发改价管(2012)020号)】-上海市发展改革委-f559.md", "level": "省"}, {"pid": "P_2013_BJ_cee25b16", "title": "北京市发展和改革委员会关于开展碳排放权交易试点工作的通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【北京市发展和改革委员会关于开展碳排放权交易试点工作的通知(京发改规〔2013〕5号)】-北京市人民政府-cee25b16.md", "level": "省"}, {"pid": "P_2015_BJ_c5505b70", "title": "（失效）北京市发展和改革委员会转发国家发展改革委关于降低国内 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【（失效）北京市发展和改革委员会转发国家发展改革委关于降低国内 ...(京发改〔2015〕1668号)】-北京市发展和改革委员会-c5505b70.md", "level": "省"}, {"pid": "P_2015_NDRC_3d821d6e", "title": "国家发展改革委 国家能源局关于印发电力体制改革配套文件的通知_政府信息公开_政务公开-国家发展改革委", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【国家发展改革委 国家能源局关于印发电力体制改革配套文件的通知_政府信息公开_政务公开-国家发展改革委(中发〔2015〕9号)】-政府门户.zfxxgk.ndrc.gov.cn-3d821d6e.md", "level": "国家"}, {"pid": "P_2015_NEA_73", "title": "加快电动汽车充电基础设施建设的指导意见", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【加快电动汽车充电基础设施建设的指导意见(国办发〔2015〕73号)】-国务院办公厅-1fdb.md", "level": "国家"}, {"pid": "P_2015_TJ_9ec9c169", "title": "市发展改革委关于进一步规范光伏发电项目建设管理有关事项的通知_ ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【市发展改革委关于进一步规范光伏发电项目建设管理有关事项的通知_ ...(津发改能源〔2015〕980号)】-天津市发展和改革委员会-9ec9c169.md", "level": "省"}, {"pid": "P_2016_AH_ae5294fd", "title": "安徽省能源局安徽省物价局国家能源局华东监管局关于印发《安徽省 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【安徽省能源局安徽省物价局国家能源局华东监管局关于印发《安徽省 ...(皖能源电力〔2016〕78号)】-安徽省发展和改革委员会-ae5294fd.md", "level": "省"}, {"pid": "P_2016_CQ_58e17873", "title": "重庆市能源局关于开展重庆市增量配电业务试点项目业主市场化优选 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【重庆市能源局关于开展重庆市增量配电业务试点项目业主市场化优选 ...(发改经体〔2016〕2120号)】-重庆市发展和改革委员会-58e17873.md", "level": "省"}, {"pid": "P_2016_HI_3bac5b3a", "title": "海南省发展和改革委员会关于印发《海南省电动汽车充电基础设施 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【海南省发展和改革委员会关于印发《海南省电动汽车充电基础设施 ...(琼发改交能〔2016〕1697号)】-海南省发展和改革委员会-3bac5b3a.md", "level": "省"}, {"pid": "P_2016_NDRC_8890ad14", "title": "关于规范开展增量配电业务改革试点的通知(发改经体〔2016〕2480号)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【关于规范开展增量配电业务改革试点的通知(发改经体〔2016〕2480号)(发改经体〔2016〕2480号)】-国家发展和改革委员会-8890ad14.md", "level": "国家"}, {"pid": "P_2017_CQ_c8d99857", "title": "重庆市能源局关于报送第二批增量配电业务改革试点项目的通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【重庆市能源局关于报送第二批增量配电业务改革试点项目的通知(渝能源电〔2017〕61号)】-重庆市发展和改革委员会-c8d99857.md", "level": "省"}, {"pid": "P_2017_GD_406db0aa", "title": "广东省发展改革委关于印发广东省2017 年度碳排放配额分配实施 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【广东省发展改革委关于印发广东省2017 年度碳排放配额分配实施 ...(粤发改气候函〔2017〕4509号)】-广东省发展和改革委员会-406db0aa.md", "level": "省"}, {"pid": "P_2017_NDRC_09206e37", "title": "电力需求侧管理办法(2017年修订版)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【电力需求侧管理办法(2017年修订版)】-国家发展改革委等六部门-dd8c.md", "level": "国家"}, {"pid": "P_2018_NDRC_ce8700fb", "title": "【关于印发《清洁能源消纳行动计划(2018-2020年)》的通知(发改 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【【关于印发《清洁能源消纳行动计划(2018-2020年)》的通知(发改 ...(发改能源规〔2018〕1575号)】-国家发展和改革委员会-ce8700fb.md", "level": "国家"}, {"pid": "P_2019_NDRC_0720b570", "title": "关于建立健全可再生能源电力消纳保障机制的通知(发改能源〔2019〕807号)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【关于建立健全可再生能源电力消纳保障机制的通知(发改能源〔2019〕807号)(发改能源〔2019〕807号)】-国家发展和改革委员会-0720b570.md", "level": "国家"}, {"pid": "P_2020_HE_6d08b05b", "title": "政府公报- 邯郸市信息公开 - 邯郸市人民政府", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【政府公报- 邯郸市信息公开 - 邯郸市人民政府(邯政字〔2020〕17号)】-政府门户.www.hd.gov.cn-6d08b05b.md", "level": "市"}, {"pid": "P_2020_NDRC_06306aac", "title": "电力中长期交易基本规则(暂行)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【电力中长期交易基本规则(暂行)】-国家发展和改革委员会、国家能源局-eaa5.md", "level": "国家"}, {"pid": "P_2021_NDRC_0421ce4f", "title": "关于加快推动新型储能发展的指导意见(征求意见稿)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【关于加快推动新型储能发展的指导意见(征求意见稿)】-国家发展改革委、国家能源局-0a44.md", "level": "国家"}, {"pid": "P_2017_GD_70875d73", "title": "广州市工业和信息化委关于印发进一步加强电动汽车充电基础设施建设运营管理的通知 - 广州市人民政府门户网站", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【广州市工业和信息化委关于印发进一步加强电动汽车充电基础设施建设运营管理的通知 - 广州市人民政府门户网站(穗工信规字〔2017〕2号)】-政府门户.www.gz.gov.cn-70875d73.md", "level": "市"}, {"pid": "P_2017_NDRC_d5bc4c87", "title": "【关于试行可再生能源绿色电力证书核发及自愿认购交易制度的通知(发改能源〔2017〕132号)】-国家发展和改革委员会", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【【关于试行可再生能源绿色电力证书核发及自愿认购交易制度的通知(发改能源〔2017〕132号)】-国家发展和改革委员会(发改能源〔2017〕132号)】-国家发展和改革委员会-d5bc4c87.md", "level": "国家"}, {"pid": "P_2018_GD_3e8388c2", "title": "充电基础设施补贴资金管理办法的通知 - 广州市人民政府", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【充电基础设施补贴资金管理办法的通知 - 广州市人民政府(穗工信规字〔2018〕3号)】-政府门户.www.gz.gov.cn-3e8388c2.md", "level": "市"}, {"pid": "P_2019_GD_0c52cbb8", "title": "广州市海珠区科技工业商务和信息化局关于开展2019-2021年度电动 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【广州市海珠区科技工业商务和信息化局关于开展2019-2021年度电动 ...】-政府门户.www.haizhu.gov.cn-0c52cbb8.md", "level": "区"}, {"pid": "P_2019_GD_781f09c6", "title": "广州市工业和信息化局关于印发进一步加强电动汽车充电基础设施建设运营管理的通知 - 广州市人民政府门户网站", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【广州市工业和信息化局关于印发进一步加强电动汽车充电基础设施建设运营管理的通知 - 广州市人民政府门户网站(穗工信规字〔2019〕1号)】-政府门户.www.gz.gov.cn-781f09c6.md", "level": "市"}, {"pid": "P_2020_SH_39_b", "title": "新能源汽车产业发展规划(2021—2035年)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【新能源汽车产业发展规划(2021—2035年)(国办发〔2020〕39号)】-国务院办公厅-9884.md", "level": "市"}, {"pid": "P_2020_SX_a009034f", "title": "陵川县人民政府办公室关于2019年贯彻落实国发42号文件重点工作的 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【陵川县人民政府办公室关于2019年贯彻落实国发42号文件重点工作的 ...(陵政办发〔2019〕44号)】-政府门户.xxgk.lczf.gov.cn-a009034f.md", "level": "县"}, {"pid": "P_2021_AH_1001d59f", "title": "六安市成品油零售网点“十四五”发展规划(征求意见稿)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【六安市成品油零售网点“十四五”发展规划(征求意见稿)】-六安市商务局-45a0.md", "level": "市"}, {"pid": "P_2025_NDRC_101520b2", "title": "电动汽车充电设施服务能力「三年倍增」行动方案(2025—2027年)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【电动汽车充电设施服务能力「三年倍增」行动方案(2025—2027年)】-国家发展和改革委员会、国家能源局-6066.md", "level": "国家"}, {"pid": "P_2025_NDRC_910", "title": "关于开展零碳园区建设的通知", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【关于开展零碳园区建设的通知(发改环资〔2025〕910号)】-国家发展改革委-2458.md", "level": "国家"}, {"pid": "P_2024_NDRC_1721", "title": "加强新能源汽车与电网融合互动的实施意见", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【加强新能源汽车与电网融合互动的实施意见(发改能源〔2023〕1721号)】-国家发展改革委等部门-8a92.md", "level": "国家"}, {"pid": "P_2024_SD_3363e0d7", "title": "山东省发展和改革委员会 监测分析 虚拟电厂提速发展助力平衡电力供需", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【山东省发展和改革委员会 监测分析 虚拟电厂提速发展助力平衡电力供需】-山东省发展和改革委员会-3363e0d7.md", "level": "省"}, {"pid": "P_2022_CQ_229620a1", "title": "重庆市发展和改革委员会关于市五届人大五次会议第0630号建议办理 ...", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【重庆市发展和改革委员会关于市五届人大五次会议第0630号建议办理 ...】-重庆市发展和改革委员会-229620a1.md", "level": "省"}, {"pid": "P_2026_SD_7440c4a3", "title": "山东省发展和改革委员会工作信息山东探索出独具特色电改路", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【山东省发展和改革委员会工作信息山东探索出独具特色电改路】-山东省发展和改革委员会-7440c4a3.md", "level": "省"}, {"pid": "P_2026_CQ_0275a8b2", "title": "重庆市能源局关于市六届人大四次会议第1123号建议协办意见的函", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【重庆市能源局关于市六届人大四次会议第1123号建议协办意见的函】-重庆市发展和改革委员会-0275a8b2.md", "level": "省"}, {"pid": "P_2023_NDRC_092751f2_a", "title": "电力需求侧管理办法(2023年版)", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【电力需求侧管理办法(2023年版)】-国家发展和改革委员会等六部门-7611.md", "level": "国家"}, {"pid": "P_2024_NEA_93_a", "title": "国家能源局关于支持电力领域新型经营主体创新发展的指导意见", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【国家能源局关于支持电力领域新型经营主体创新发展的指导意见(国能发法改〔2024〕93号)】-国家能源局-381e.md", "level": "国家"}, {"pid": "P_2024_JL_232", "title": "关于促进吉林省用户侧储能设施建设的若干措施", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【关于促进吉林省用户侧储能设施建设的若干措施(吉能储能〔2024〕232号)】-吉林省能源局、发改委、工信厅-982e.md", "level": "省"}, {"pid": "P_2025_GO_d433682b", "title": "最高补20万元！福建宁德市推广集中式“光储充检”一体化示范站", "path": "/Users/shaoziyuan/Documents/Zayn Main/政策分析/0_raw/policies/【最高补20万元！福建宁德市推广集中式“光储充检”一体化示范站】-未知机构-d433682b.md", "level": "国家"}]
log(`载入 ${policies.length} 篇待标;每篇由 opus/sonnet/haiku 三模型独立标`)

const MODELS = ['opus', 'sonnet', 'haiku']
const results = await pipeline(policies,
  async (pol) => {
    const labels = await parallel(MODELS.map(m => () =>
      agent(buildPrompt(pol), { label: `${m}:${pol.pid}`, phase: 'Label', model: m, schema: LABEL_SCHEMA })
        .then(r => ({ model: m, label: r }))))
    return { pol, labels: (labels || []).filter(x => x && x.label) }
  },
  ({ pol, labels }) => consensus(pol, labels),
)

const byLevel = { high: 0, mid: 0, low: 0, failed: 0 }
for (const r of results) byLevel[r.agreement] = (byLevel[r.agreement] || 0) + 1
log(`标完:high ${byLevel.high} · mid ${byLevel.mid} · low(需裁) ${byLevel.low} · failed ${byLevel.failed}`)
return { count: results.length, by_level: byLevel, results }
