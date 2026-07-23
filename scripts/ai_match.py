"""AI 匹配模块：用户画像 -> 险种推荐方案（DeepSeek，合规边界内）。"""
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
        out = recommend(p)
        results.append({"profile": p, "result": json.loads(out)})
    except Exception as e:
        results.append({"profile": p, "error": str(e)})

with open("insurance/data/ai_match_demo.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("done, profiles:", len(results))
for r in results:
    if "result" in r:
        recs = r["result"].get("recommendations", [])
        types = [x.get("insurance_type", "") for x in recs]
        print(f"  {r['profile']['name']}: {len(recs)}项 -> {types}")
    else:
        print(f"  {r['profile']['name']}: ERROR {r.get('error')}")
