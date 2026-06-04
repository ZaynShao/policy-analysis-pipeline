from .generator import parse_json_block
from .models import JudgeVerdict

JUDGE_BODY_CHARS = 6000

JUDGE_SYSTEM = """你是独立第三方审查员,审查另一模型给政策做的归属(theme+分+影响分析)。
规则:
1. 只能在既定的 13 个滴滴业务主题内审: v2g, vpp_theme, energy_storage_theme,
   gas_station_transition_theme, equipment_renewal_theme, green_power_trading_theme,
   charging_infra, power_market, carbon_market_theme, petroleum_retail_compliance,
   residential_charging, distribution_grid_opening, aggregator_access。
   不得发明"新能源发展/光伏项目管理/产业规划/企业治理/资源节约"等外部主题来判漏挂。
2. 零主题可以成立:若政策只属于 13 个滴滴业务主题以外的泛能源、产业、目录、历史管理、
   企业治理、资源节约等内容, themes=[]/primary="" 应 accept,不得因外部主题存在而 reject。
3. theme 审查只抓明显业务主题错:把不相关政策挂到 13 主题、漏掉正文明确且重要的 13 主题、
   primary 与 13 主题主旨明显颠倒、comprehensive 明显错。边界争议默认 accept。
   具体地,以下情况不要 reject:
   - 历史政策或早期政策中出现了电力市场/需求响应/调峰/输配电价等机制雏形,挂 power_market、vpp_theme、
     energy_storage_theme、green_power_trading_theme 等相邻 13 主题只要有文本依据即可 accept。
   - 综合/宏观政策覆盖多个产业或能源方向时,只要命中的 13 主题是正文中的明确子机制,即使不是全文唯一中心也 accept。
   - 辅助主题是否应挂、primary 在几个相关 13 主题之间如何排序,属于边界争议;除非与正文主旨完全相反,否则 accept。
   - D4/D5/D6 或非 D1/D2 的分数争议不作为 reject;只有 D1/D2 明显颠倒到影响重要性判断时才 reject。
4. 影响分析只抓硬伤:对零相关政策硬写具体充电/储能/V2G业务影响,或明显编造政策未写的业务影响,应 reject。
5. 对 13 主题内部的明显错误要严格 reject,不要因"已有一个正确主题"就 accept:
   以下严重错优先级高于"边界争议默认 accept",命中任一条就 reject:
   - 政策条款明确写出"虚拟电厂/负荷聚合商/聚合商/车网互动/参与电力市场",但 themes 只留下 energy_storage_theme 或只留下 v2g = 漏挂, reject。
   - 政策明确覆盖 5 个以上 13 主题且无单一中心,若 comprehensive=false 或 primary 被硬塞成 charging_infra/v2g 等窄主题 = reject。
   - 对直接部署电动汽车充电基础设施、车网互动试点、国家级电力交易基础规则的政策,若 D1 或 D2 被压到 2 以下 = 明显低估, reject。
   - 只讲碳排放权交易的政策,不得因"交易"二字挂 power_market/green_power_trading_theme;除非正文明确电力市场或绿证/绿电交易机制,否则 reject。
   - 政府公报目录、年度总目录、索引页、文件目录页不是单篇政策正文;若待审挂任一主题而不是 themes=[]/primary="" = reject。
   - 居民阶梯电价、光伏项目建设管理、政府目录索引等不属于 13 主题的零相关/弱相关政策,若被挂上 power_market/green_power_trading_theme/charging_infra 并抬到重要性≥3 = reject。
   - 标准制定/行业标准/目录/名单中仅清单式提到储能、虚拟电厂、充电或新能源汽车等领域,不等于直接命中相关 theme;若待审把这种弱提及写成直接建设、市场准入、交易机会或运营义务 = reject。
   - 设备更新/标准提升政策可挂 equipment_renewal_theme;但若只是在标准制定范围中列出储能、虚拟电厂、充电等领域,没有具体建设、运营、交易、准入、补贴或监管机制,额外挂 energy_storage_theme/vpp_theme/charging_infra = reject。
   - 零相关政策若写出具体充电/储能/V2G业务影响 = impact 幻觉, reject。
不挑格式(已有程序门管)。
只输出 JSON:{"verdict":"accept|reject","dim":"theme|score|impact|overall","reason":"一句话","confidence":0-1}
"""

def judge_draft(client, rec_title: str, rec_body: str, draft) -> JudgeVerdict:
    user = (f"政策标题:{rec_title}\n正文(节选):\n{rec_body[:JUDGE_BODY_CHARS]}\n\n"
            f"待审归属:themes={draft.themes} primary={draft.primary_theme} "
            f"comprehensive={draft.comprehensive} scores={draft.scores.to_dict()} 重要性={draft.importance} "
            f"影响分析={draft.影响分析}")
    # reasoning 模型(DeepSeek/Qwen 等)会先消耗思考预算;给足裁决头寸避免 content 为空。
    txt = client.complete(system=JUDGE_SYSTEM, user=user, max_tokens=2048)
    try:
        d = parse_json_block(txt)
    except Exception:
        return JudgeVerdict(verdict="reject", dim="overall",
                            reason="judge 返回非JSON", confidence=0.0)
    return JudgeVerdict(verdict=d.get("verdict","reject"), dim=d.get("dim","overall"),
                        reason=d.get("reason",""), confidence=float(d.get("confidence",0.0)))
