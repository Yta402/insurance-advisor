"""LLM 条款要素抽取：从重疾险条款文本抽取结构化要素，入库 products 表。

这是选型表里"产品条款要素抽取=LLM（真AI）"的落地。
条款文本基于公开产品结构特征整理（非实时费率）；保费待官网采集补全。
合规：只抽取客观保障结构，不做产品推荐。
"""
import json
import os
import sqlite3
from openai import OpenAI

client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
DB = "insurance/data/complaints.db"

# 代表性重疾险条款摘要（基于公开产品结构特征整理，非精确费率）
PRODUCT_TERMS = [
    {
        "product_name": "超级玛丽（互联网消费型重疾）",
        "company": "君龙人寿",
        "raw_terms": "保障期间可选保至70岁或终身。重疾确诊赔付1次，赔付基本保额。"
                     "含中症（赔付60%保额）与轻症（赔付30%保额），中轻症豁免后续保费。"
                     "身故责任可选（不含身故则退还现金价值）。等待期180天。健康告知相对宽松。"
                     "无返还，属消费型。",
    },
    {
        "product_name": "达尔文（互联网消费型重疾）",
        "company": "瑞华健康",
        "raw_terms": "保障期间可选保至70岁或终身。重疾确诊赔付1次。"
                     "含中症与轻症，中轻症豁免保费。可选癌症多次赔付（间隔期3年）。"
                     "身故责任可选。等待期180天。消费型，无返还。",
    },
    {
        "product_name": "平安福（储蓄型重疾）",
        "company": "平安人寿",
        "raw_terms": "保障期间为终身。重疾确诊赔付1次。含中症轻症。"
                     "身故责任为必选（含身故赔付保额），故保费显著高于消费型。"
                     "等待期90天。属储蓄型（含身故），现金价值随时间增长。无满期返还。",
    },
]

SCHEMA = """输出严格 JSON，字段：
{"form":"消费型/储蓄型/返还型","term":"保障期间","ci_payout":"重疾赔付次数与方式",
 "mid_light":"中症轻症及赔付比例","death":"身故责任(必选/可选/无)","waiting_period":"等待期",
 "health_notice":"健康告知宽松度(宽松/中等/严格)","returnable":"是否满期返还(是/否)",
 "key_risk":"最需消费者关注的条款风险点(一句话)"}"""


def extract(terms_text):
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是保险条款结构化抽取器。" + SCHEMA},
            {"role": "user", "content": f"抽取以下条款的结构化要素：\n{terms_text}"},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS products (
    product_name TEXT, company TEXT, form TEXT, term TEXT, ci_payout TEXT,
    mid_light TEXT, death TEXT, waiting_period TEXT, health_notice TEXT,
    returnable TEXT, key_risk TEXT, data_version TEXT,
    PRIMARY KEY (product_name))""")

results = []
for p in PRODUCT_TERMS:
    try:
        fields = extract(p["raw_terms"])
        cur.execute("INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["product_name"], p["company"], fields.get("form", ""), fields.get("term", ""),
                     fields.get("ci_payout", ""), fields.get("mid_light", ""), fields.get("death", ""),
                     fields.get("waiting_period", ""), fields.get("health_notice", ""),
                     fields.get("returnable", ""), fields.get("key_risk", ""), "示例-基于公开结构特征"))
        results.append({"product": p["product_name"], "company": p["company"], "fields": fields})
    except Exception as e:
        results.append({"product": p["product_name"], "error": str(e)})
con.commit()

# 关联验证：products.company 是否在投诉库
print("extracted products:", len([r for r in results if "fields" in r]))
for r in results:
    if "fields" in r:
        f = r["fields"]
        in_db = cur.execute("SELECT 1 FROM complaints WHERE company=? LIMIT 1", (r["company"],)).fetchone()
        link = "OK-linked" if in_db else "NO-link"
        print(f"  {r['product']} ({r['company']}): form={f.get('form')} | death={f.get('death')} | {link}")
    else:
        print(f"  {r['product']}: ERROR {r.get('error')}")
con.close()

with open("insurance/data/products_extracted.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
