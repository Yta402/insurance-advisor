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
    {
        "product_name": "康惠保（消费型重疾）",
        "company": "百年人寿",
        "raw_terms": "保障期间可选保至70岁或终身。重疾确诊赔付1次。含中症与轻症，"
                     "中轻症豁免后续保费。身故责任可选。等待期180天。消费型，无返还，"
                     "互联网渠道销售，健康告知中等。",
    },
    {
        "product_name": "健康保普惠多倍版（多次赔消费型）",
        "company": "昆仑健康",
        "raw_terms": "保障期间可选保至70岁或终身。重疾可不分组多次赔付（间隔期1年），"
                     "这是其核心差异点。含中症轻症。身故责任可选。等待期180天。"
                     "消费型，无返还。保费高于单次赔消费型，但重疾可多次获赔。",
    },
    {
        "product_name": "国寿福（储蓄型重疾）",
        "company": "中国人寿",
        "raw_terms": "保障期间为终身。重疾确诊赔付1次。含中症轻症。"
                     "身故责任为必选（含身故赔付保额），保费较高，属传统大公司储蓄型。"
                     "等待期180天。现金价值随时间增长。无满期返还。品牌溢价明显。",
    },
    {
        "product_name": "金佑人生（储蓄型含分红）",
        "company": "太平洋人寿",
        "raw_terms": "保障期间为终身。重疾确诊赔付1次。身故责任必选。"
                     "含分红功能（保额随分红增长），但分红非保证。保费高。"
                     "等待期180天。属储蓄型+分红，现金价值增长但前期退保损失大。无满期返还。",
    },
    {
        "product_name": "某两全返还型重疾（返还型）",
        "company": "太平人寿",
        "raw_terms": "保障期间至约定年龄（如至70/80岁）。重疾确诊赔付1次。身故责任含。"
                     "核心特征：若保障期内未发生重疾理赔，满期返还已交保费或约定金额（如返还保额）。"
                     "保费显著高于消费型（多交的钱本质是储蓄）。等待期90-180天。属返还型，"
                     "兼顾保障与满期领回，但保障杠杆低于消费型。",
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
