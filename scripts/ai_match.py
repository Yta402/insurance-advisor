"""AI 匹配模块：用户画像 -> 险种推荐方案（DeepSeek）+ 规则校验兜底。

设计原则：LLM 负责"多约束推理+个性化解释"，规则层负责"合规红线+合理性校验"。
LLM 输出不可全信，必须有规则校验兜底（防止越界推荐理财型、漏掉高龄劝退等）。
"""
import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

SYSTEM = """你是保险决策辅助工具。基于用户画像，推荐适合的健康保障险种组合。
严格合规：
- 只做险种层面的信息建议，不推荐具体产品，不代核保，不给投保指令
- 排除理财型(年金/增额终身寿)、财险、定期寿险
- 45岁以上重疾险若保费倒挂(总保费接近或超过保额)，须诚实劝退，导向医疗+意外
- 全程"建议/可考虑"措辞，决策权在用户

可选险种：百万医疗险、意外险、重疾险(消费型/储蓄型/返还型)。

输出严格 JSON：
{"recommendations":[{"insurance_type":"险种","form":"形态(若有)","reason":"推荐理由","sum_insured_range":"建议保额区间","priority":"高/中","annual_budget":"建议年保费区间"}],"notes":"合规与个性化提示"}"""

ALLOWED_TYPES = {"百万医疗险", "意外险", "重疾险"}
ALLOWED_CI_FORMS = {"消费型", "储蓄型", "返还型", ""}
PRIORITY_RANK = {"高": 0, "中": 1, "低": 2}
WARN_KEYWORDS = ["保费倒挂", "劝退", "放弃重疾", "不建议.*重疾", "优先.*医疗"]


def recommend(profile):
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"用户画像：{json.dumps(profile, ensure_ascii=False)}"},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def validate(raw, profile):
    """规则校验 LLM 输出：险种白名单、去重、形态合规、高龄重疾劝退检查。"""
    warnings = []
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception as e:
            return None, [f"LLM 输出非合法 JSON: {e}"]
    else:
        data = raw
    recs = data.get("recommendations", [])
    notes = data.get("notes", "")

    # 1) 险种白名单过滤 + 去重（同险种保留优先级最高）
    seen = {}
    dropped = []
    for r in recs:
        t = r.get("insurance_type", "")
        if t not in ALLOWED_TYPES:
            dropped.append(t)
            continue
        # 重疾形态合规
        if t == "重疾险":
            form = r.get("form", "")
            if form and form not in ALLOWED_CI_FORMS:
                r["form"] = "消费型"
                warnings.append(f"重疾形态'{form}'不合规，已重置为消费型")
        # 去重
        if t in seen:
            old_pri = PRIORITY_RANK.get(seen[t].get("priority", "中"), 1)
            new_pri = PRIORITY_RANK.get(r.get("priority", "中"), 1)
            if new_pri < old_pri:
                seen[t] = r
        else:
            seen[t] = r
    if dropped:
        warnings.append(f"过滤越界险种: {dropped}")
    clean_recs = list(seen.values())

    # 2) 高龄重疾劝退校验（age>=45 且含重疾，必须 notes 有劝退提示）
    age = profile.get("age", 0)
    has_ci = any(r["insurance_type"] == "重疾险" for r in clean_recs)
    import re
    if age >= 45 and has_ci:
        if not any(re.search(k, notes) for k in WARN_KEYWORDS):
            notes = ("【规则校验补充】该年龄段({}岁)重疾险存在保费倒挂风险，"
                     "若总保费接近保额建议放弃重疾、将预算转向提高医疗险/意外险保额。").format(age) + " " + notes
            warnings.append("高龄重疾缺少劝退提示，规则层已补")

    data["recommendations"] = clean_recs
    data["notes"] = notes
    data["_validation_warnings"] = warnings
    return data, warnings


profiles = [
    {"name": "24岁应届生", "age": 24, "income": "低(应届月薪8k)",
     "family": "单身", "health": "健康", "budget": "2000元/年"},
    {"name": "38岁家庭支柱(小姨画像)", "age": 38, "income": "中高(银行工作)",
     "family": "已婚有孩", "health": "亚健康(长期高压)", "budget": "10000元/年"},
    {"name": "55岁中年", "age": 55, "income": "中",
     "family": "已婚孩子成年", "health": "有高血压慢性病", "budget": "5000元/年"},
]
results = []
for p in profiles:
    try:
        raw = recommend(p)
        validated, warns = validate(raw, p)
        results.append({"profile": p, "result": validated, "raw_llm": raw if isinstance(raw, str) else None})
    except Exception as e:
        results.append({"profile": p, "error": str(e)})

with open("insurance/data/ai_match_demo.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("done, profiles:", len(results))
for r in results:
    if "result" in r and r["result"]:
        recs = r["result"].get("recommendations", [])
        types = [x.get("insurance_type", "") for x in recs]
        w = r["result"].get("_validation_warnings", [])
        print(f"  {r['profile']['name']}: {len(recs)}项 -> {types} | warns:{len(w)}")
    else:
        print(f"  {r['profile']['name']}: ERROR {r.get('error')}")
