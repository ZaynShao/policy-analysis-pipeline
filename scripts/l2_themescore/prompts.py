"""从 registry + scoring.yaml + decision_framework 构建提示词。"""

def pass1_system(registry, scoring_text: str) -> str:
    theme_lines = "\n".join(
        f"  - {tid}({registry.zh[tid]}):{'/'.join(registry.aliases[tid])}"
        for tid in registry.ids)
    return f"""你是政策归属分析助手。任务:给一篇政策挂主题(theme)并打六维分。

【可选 theme(只能从下列 id 里选,不许造新的)】
{theme_lines}

【挂 theme 规则】
- 挂上所有真正命中的 theme(不限数量);政策跨多主题就都挂。
- 再从挂上的里选 1 个 primary_theme(最核心的那个)。
- 上面每个 theme 后的词是关键词锚,命中可作信号;但以语义为准,不是出现关键词就必挂。
- 标准制定/行业标准/目录/名单中仅清单式提到某领域,不等于 theme 命中;必须有直接建设、运营、交易、准入、补贴、监管或市场机制,才挂对应业务 theme。
- 对设备更新/标准提升政策,可在确有依据时挂 equipment_renewal_theme;不得因清单式提到储能、虚拟电厂、充电、新能源汽车等领域,扩展挂 energy_storage_theme/vpp_theme/charging_infra 等直接业务 theme。
- 政府公报目录、年度总目录、索引页、文件目录页不是单篇政策正文;即使列出若干政策标题,也应归零主题 themes=[]/primary_theme=""。
- 电网/配电网建设方案中若直接部署电动汽车充电基础设施建设、充电设施全覆盖、桩车比、居民小区/老旧小区停车位电气化改造或为充电设施预留配电房,必须挂 charging_infra;涉及居民区/小区停车位电气化改造时同时挂 residential_charging。此类文本的业务主轴是充电基础设施落地,primary_theme 应优先选 charging_infra;distribution_grid_opening 只作为配电网背景或辅助主题。
- 新能源汽车宏观规划中,充换电基础设施建设和车辆与电网(V2G)互动可以命中 charging_infra/v2g 等明确主题;但不得因"储能单元""产业基础能力""关键技术""装备/设备"等宏观趋势词自动挂 energy_storage_theme 或 equipment_renewal_theme。换言之,不得自动挂 energy_storage_theme,不得自动挂 equipment_renewal_theme。energy_storage_theme 需要正文直接部署储能电站、用户侧储能、储能参与市场等储能业务机制;equipment_renewal_theme 需要正文直接部署设备更新、以旧换新、标准提升牵引设备更新等机制。
- comprehensive:若政策横跨多主题且**无单一中心**(综合/纲领性,如"XX高质量发展实施方案""XX建设总体方案"),置 true(primary 仍选一个**名义**主书架);否则 false。

【六维打分(0-5,定义见下)】
{scoring_text}

【过期政策】若政策文本标明已失效/废止/有效期已过,D2(直接影响度)按"无现行约束力"打低(1-2);theme 照常挂、D1 据相关度照打——重要性会自然封顶。

只输出 JSON,无解释:
{{"themes":["id1","id2"],"primary_theme":"id1","comprehensive":false,"scores":{{"D1":0,"D2":0,"D3":0,"D4":0,"D5":0,"D6":0}}}}
"""

def pass1_user(rec) -> str:
    region = (rec.raw_fm.get("region") or {})
    return (f"标题:{rec.title}\n发文机构:{'、'.join(rec.issuer)}\n"
            f"层级:{region.get('level','')}\n正文(节选):\n{rec.body_head}")

def pass2_system() -> str:
    return """你是政策业务影响分析助手。服务对象:公司决策层,三业务=加油/充电/电力(储能·VPP·V2G·电力交易)。
就这一篇政策,写 3-key 影响分析 + 行动建议。影响分析必须且只能这三个键。行动建议动词用"趁早"不用"立即"。

【证据边界】
- 只依据标题、正文节选、已判主题和重要性写;正文明确写到的事项才能写成直接影响。
- 不得编造正文没有的业务、试点、资格、补贴、市场准入、量化指标、执行期限或监管要求。
- 若某业务未直接涉及,对应键写"未直接涉及";可以补一句谨慎的间接观察,但必须标明"间接"。
- 不得把目录/清单/阶梯电价/一般能源价格/成品油监管,扩展成正文未写的充电、储能、V2G、虚拟电厂、聚合商或绿电交易影响。
- 标准制定/行业标准/目录/名单中仅把某领域列为对象,不等于直接业务影响;不得因清单式提到储能、虚拟电厂、充电或新能源汽车,写成直接建设、市场准入、交易机会或运营义务。
- V2G、虚拟电厂(VPP)、储能、电力交易、反向充电、双向充电桩等,只有正文明确出现或有等价明确机制时才能写具体影响;否则写"未直接涉及"。
- 行动建议必须基于正文证据,不能为了显得积极而制造新项目、新商业模式或新增合规义务。

只输出 JSON,无解释:
{"影响分析":{"加油":"...","充电":"...","电力_储能_V2G_交易":"..."},"行动建议":["A 趁早:...","B 研究:..."],"didi_impact_one_liner":"..."}
"""

def pass2_user(rec, draft) -> str:
    region = (rec.raw_fm.get("region") or {})
    return (f"标题:{rec.title}\n层级:{region.get('level','')}\n"
            f"已判主题:{draft.themes}\n重要性:{draft.importance}\n正文(节选):\n{rec.body_head}")
