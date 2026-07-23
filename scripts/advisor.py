"""端到端顾问：用户画像 -> 险种推荐(校验) -> 产品匹配 -> 公司服务质量关联 -> 综合方案。

集成三层数据：
1. AI 险种推荐（LLM + 规则校验）
2. 产品匹配（products 表，SQL 筛选）
3. 公司服务质量（complaints 表，SQL 关联）

输出为决策辅助信息，不构成投保建议。
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_match import recommend, validate

DB = "insurance/data/complaints.db"


def match_products(con, insurance_type, form=None):
    """按险种匹配 products 表。重疾险返回所有形态（消费/储蓄/返还）便于对比。
    不按推荐形态硬过滤——让用户看到消费vs储蓄对比，且储蓄型（大公司）能关联投诉库。"""
    if insurance_type != "重疾险":
        return []  # 当前产品库仅含重疾险，医疗/意外待扩充
    sql = ("SELECT product_name, company, form, death, waiting_period, "
           "health_notice, key_risk FROM products ORDER BY form")
    rows = [dict(r) for r in con.execute(sql).fetchall()]
    return rows


def company_service_quality(con, company):
    """关联公司最新季度的投诉指标（服务质量代理指标）。"""
    row = con.execute(
        "SELECT quarter, value FROM complaints WHERE company=? AND metric='per_premium' "
        "ORDER BY quarter DESC LIMIT 1", (company,)).fetchone()
    if not row:
        return None
    # 人身险亿元保费投诉量行业基准（2023Q1 中位数约1.0）
    benchmark = 1.0
    val = row["value"]
    if val > benchmark * 3:
        level = "偏高（显著高于行业中位数）"
    elif val > benchmark * 1.5:
        level = "中等偏高"
    else:
        level = "接近或低于行业中位数"
    return {"quarter": row["quarter"], "per_premium": val, "level": level}


def advise(profile, con):
    """端到端：画像 -> 推荐 -> 匹配 -> 关联。"""
    raw = recommend(profile)
    plan, warns = validate(raw, profile)
    if plan is None:
        return {"error": "LLM 输出校验失败", "warnings": warns}

    enriched = []
    for rec in plan.get("recommendations", []):
        item = dict(rec)
        prods = match_products(con, rec["insurance_type"], rec.get("form"))
        # 关联每个产品对应公司的服务质量
        for p in prods:
            sq = company_service_quality(con, p["company"])
            p["service_quality"] = sq if sq else {
                "note": "该公司未在监管投诉通报上榜（通报仅列投诉较高的前若干家，非全市场；未上榜不等于无投诉）"}
        item["matched_products"] = prods
        if not prods:
            item["product_match_note"] = "当前产品库暂无该险种样本，待扩充采集"
        enriched.append(item)

    plan["recommendations"] = enriched
    plan["_validation_warnings"] = warns
    plan["_disclaimer"] = ("本输出仅为信息呈现与对比，不构成投保建议；"
                           "健康告知需如实向保险公司申报，投保决策由用户自行作出。")
    return plan


if __name__ == "__main__":
    test_profiles = [
        {"name": "38岁家庭支柱(小姨画像)", "age": 38, "income": "中高(银行工作)",
         "family": "已婚有孩", "health": "亚健康(长期高压)", "budget": "10000元/年"},
        {"name": "55岁中年", "age": 55, "income": "中",
         "family": "已婚孩子成年", "health": "有高血压慢性病", "budget": "5000元/年"},
    ]
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    outputs = []
    for p in test_profiles:
        try:
            res = advise(p, con)
            outputs.append({"profile": p, "result": res})
            recs = res.get("recommendations", []) if isinstance(res, dict) else []
            types = [r.get("insurance_type") for r in recs]
            nprod = sum(len(r.get("matched_products", [])) for r in recs)
            print(f"  {p['name']}: recs={types} | matched_products={nprod} | warns={len(res.get('_validation_warnings',[]))}")
        except Exception as e:
            outputs.append({"profile": p, "error": str(e)})
            print(f"  {p['name']}: ERROR {e}")
    con.close()
    with open("insurance/data/advisor_demo.json", "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)
    print("advisor end-to-end done")
