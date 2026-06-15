"""存量 date 误标回填 oneshot 的决策逻辑 + §C 写回 测试。

口径(用户拍板:保守自动修 + 其余入队):
- 自动修 date,仅当 date "可证为错"(生效/截止误标 / 未来年 / 破损)且能抽到可信落款发文日。
- 错但抽不到落款 → 入队。
- 合理且非误标的 date(哪怕与落款不同)→ 不动(信任,误伤≈零)。
- 年份变 → 重算 id,旧 id 入 aliases。official_number 只标记不写。
"""
from __future__ import annotations
import yaml
from scripts._oneshot.date_issuance_backfill import (
    decide, compute_new_id, apply_to_file,
)


def _fm(**kw):
    base = {"id": "P_2026_X_1", "date": "", "official_number": ""}
    base.update(kw)
    return base


# ── decide:自动修 ───────────────────────────────────────────
def test_same_year_effective_mislabel_fixes_date_no_id_change():
    body = ("二、本通知自2026年7月1日起执行。《...》（浙发改价格〔2024〕21号）同时废止。\n"
            "浙江省发展和改革委员会 浙江省能源局\n2026年5月28日")
    d = decide(_fm(id="P_2026_ZJ_FGW_21", date="2026-07-01",
                   official_number="浙发改价格〔2024〕21号"), body, today_year=2026)
    assert d.action == "fix"
    assert d.new_date == "2026-05-28"
    assert d.new_id is None            # 同年 → 不动 id
    assert d.offnum_flag is True       # 现 official_number 是废止号 → 标记


def test_deadline_mislabel_fixed():
    body = "本办法有效期至2026年12月31日。\n北京市生态环境局\n2026年1月20日"
    d = decide(_fm(id="P_2026_BJ_x", date="2026-12-31"), body, today_year=2026)
    assert d.action == "fix"
    assert d.new_date == "2026-01-20"


def test_future_year_with_chinese_luokuan_fixes_date_and_id():
    body = ("国家发展改革委 国家能源局\n二〇二三年九月\n\n"
            "第一章 总则……自2023年10月15日起施行。")
    d = decide(_fm(id="P_2027_NDRC_572b0ea8", date="2027-01-01"),
               body, today_year=2026)
    assert d.action == "fix"
    assert d.new_date == "2023-09-01"
    assert d.new_id == "P_2023_NDRC_572b0ea8"


def test_broken_empty_date_filled_from_luokuan():
    body = "国家发展改革委\n2024年3月5日"
    d = decide(_fm(id="P_1900_NDRC_abc", date=""), body, today_year=2026)
    assert d.action == "fix"
    assert d.new_date == "2024-03-05"
    assert d.new_id == "P_2024_NDRC_abc"


# ── decide:不动 / 入队 ──────────────────────────────────────
def test_plausible_non_mislabel_date_left_untouched():
    # 合理 date、不在正文做生效/截止、未破损 → 即便落款不同也不动(信任,防误伤)
    body = "济南市人民政府办公厅\n2016年3月17日"
    d = decide(_fm(id="P_2024_SD_x", date="2024-05-01"), body, today_year=2026)
    assert d.action == "noop"


def test_wrong_date_without_extractable_luokuan_queued():
    body = "没有任何落款日期的正文。自本规则印发之日起施行。"
    d = decide(_fm(id="P_2030_NDRC_x", date="2030-01-01"), body, today_year=2026)
    assert d.action == "queue"


def test_wrong_date_with_only_interaction_timestamp_queued():
    # cur 是"前"截止日(误标),但正文只有咨询互动时间戳,无可信落款 → 入队不乱改
    body = ("对于办法发布之日前已于2025年5月1日前并网投产的项目……\n"
            "| 提交时间 | 2025-11-09 |\n| 回复时间 | 2025-11-13 |")
    d = decide(_fm(id="P_2025_HA_x", date="2025-05-01"), body, today_year=2026)
    assert d.action == "queue"


def test_issue_date_equals_effective_date_not_fixed():
    # 发文日==生效日(常见):date 同时出现在生效句和落款 → 不算误标,不动(防误伤)
    body = ("本实施细则自2024年9月27日起施行,有效期至2025年3月31日。\n"
            "上海市发展改革委 上海市公安局\n2024年9月27日\n\n---\n\n_采集于 2026-04-25T11:07:53")
    d = decide(_fm(id="P_2024_SH_14", date="2024-09-27"), body, today_year=2026)
    assert d.action == "noop"


def test_deadline_qian_mislabel_fixed_to_luokuan():
    # BJ 类:date 是 "X日前" 任务截止 → 误标,修到落款发文日
    body = ("2026年12月31日前，重点碳排放单位应报送数据。特此通知。\n"
            "北京市生态环境局\n2026年3月18日")
    d = decide(_fm(id="P_2026_BJ_559a203d", date="2026-12-31"), body, today_year=2026)
    assert d.action == "fix"
    assert d.new_date == "2026-03-18"


def test_offnum_not_flagged_when_clean():
    body = "（发改能源〔2024〕1128号）规定……\n国家发展改革委\n2024年3月5日"
    d = decide(_fm(id="P_2024_NDRC_1128", date="2024-03-05",
                   official_number="发改能源〔2024〕1128号"), body, today_year=2026)
    assert d.offnum_flag is False


# ── compute_new_id ──────────────────────────────────────────
def test_compute_new_id_swaps_year():
    assert compute_new_id("P_2027_NDRC_572b0ea8", 2023, set()) == "P_2023_NDRC_572b0ea8"


def test_compute_new_id_collision_suffix():
    assert compute_new_id("P_2027_NDRC_572b0ea8", 2023,
                          {"P_2023_NDRC_572b0ea8"}) == "P_2023_NDRC_572b0ea8_a"


# ── apply_to_file:§C 写回 + 幂等 ────────────────────────────
def _write_md(tmp_path, fm: dict, body: str):
    p = tmp_path / "x.md"
    p.write_text("---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False)
                 + "---\n\n" + body + "\n", encoding="utf-8")
    return p


def test_apply_writes_date_id_aliases_and_audit_then_idempotent(tmp_path):
    fm = {"id": "P_2027_NDRC_572b0ea8", "aliases": ["P_2027_NDRC_572b0ea8"],
          "title": "t", "official_number": "", "date": "2027-01-01",
          "provenance": {"url": "u"}, "type": "policy"}
    body = "国家发展改革委 国家能源局\n二〇二三年九月\n\n自2023年10月15日起施行。"
    p = _write_md(tmp_path, fm, body)

    d = decide(fm, body, today_year=2026)
    assert d.action == "fix" and d.new_id == "P_2023_NDRC_572b0ea8"
    apply_to_file(str(p), d, now_iso="2026-06-15T12:00:00+08:00")

    out = yaml.safe_load(p.read_text(encoding="utf-8").split("---\n")[1])
    assert out["date"] == "2023-09-01"
    assert out["id"] == "P_2023_NDRC_572b0ea8"
    assert "P_2027_NDRC_572b0ea8" in out["aliases"]      # 旧 id 保留(反链)
    assert "P_2023_NDRC_572b0ea8" in out["aliases"]
    prov = out["provenance"]
    assert prov["date_fixed_from"] == "2027-01-01"
    assert prov["date_fixed_method"] == "body_chinese_date"
    assert prov["id_fixed_from"] == "P_2027_NDRC_572b0ea8"
    assert prov["id_fixed_method"] == "id_recompute_from_metadata"

    # 幂等:再决策应 noop(date 已对、年份合理)
    fm2 = yaml.safe_load(p.read_text(encoding="utf-8").split("---\n")[1])
    body2 = p.read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n")
    assert decide(fm2, body2, today_year=2026).action == "noop"
