"""混合抽取：正则主抽 + 完整度校验 + LLM 兜底（数值原文验证防幻觉）。

设计原则（AGENTS.md 选型表）：
- 正则主抽：半结构化公文，快、准、免费
- LLM 仅兜底：当正则在某季度×指标抽取为0（格式变化/异常）时触发
- 数值红线：LLM 抽取的每个数值必须在原文中正则可验证，否则丢弃（防 LLM 数字幻觉）
"""
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

BODIES = "insurance/scripts/quarterly_bodies.json"
DB = "insurance/data/complaints.db"

RATE_PATTERNS = [
    ("per_premium", "件/亿元", re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+\.\d+)件/亿元")),
    ("per_policy", "件/万张", re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+\.\d+)件/万张")),
    ("per_person", "件/万人次", re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+\.\d+)件/万人次")),
]
COUNT_SEG = re.compile(r"投诉量较[多高]的(财产保险公司|人身保险公司)为[:：]([^。]*)")
COUNT_ITEM = re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+)件")

NOISE = ["投诉量", "中位数", "保费", "亿元", "万张", "万人次", "较高", "较多",
         "为", "情况", "占", "的"]
EXPECTED_METRICS = ["per_premium", "per_policy", "per_person", "complaint_count"]


def guess_type(name):
    if any(k in name for k in ["人寿", "健康", "养老", "生命", "年金"]):
        return "人身险"
    if any(k in name for k in ["财险", "农险", "财产", "相互", "在线", "车险",
                                "信保", "责任", "航运", "建工"]):
        return "财险"
    if "保险" in name:
        return "财险"
    return "未知"


def is_valid_company(name):
    if not (2 <= len(name) <= 10):
        return False
    return not any(w in name for w in NOISE)


def regex_extract(body, quarter):
    """正则主抽。返回 records 列表 + 每指标命中计数。"""
    recs = []
    seen = set()
    metric_hits = defaultdict(int)
    for metric, unit, pat in RATE_PATTERNS:
        for m in pat.finditer(body):
            comp = m.group(1).strip()
            if not is_valid_company(comp):
                continue
            val = float(m.group(2))
            key = (quarter, comp, metric)
            if key in seen:
                continue
            seen.add(key)
            metric_hits[metric] += 1
            recs.append({"quarter": quarter, "company": comp,
                         "company_type": guess_type(comp), "metric": metric,
                         "value": val, "unit": unit})
    for m in COUNT_SEG.finditer(body):
        ctype = "财险" if "财产" in m.group(1) else "人身险"
        for mm in COUNT_ITEM.finditer(m.group(2)):
            comp = mm.group(1).strip()
            if not is_valid_company(comp):
                continue
            val = int(mm.group(2))
            key = (quarter, comp, "complaint_count")
            if key in seen:
                continue
            seen.add(key)
            metric_hits["complaint_count"] += 1
            recs.append({"quarter": quarter, "company": comp, "company_type": ctype,
                         "metric": "complaint_count", "value": val, "unit": "件"})
    return recs, metric_hits


def llm_fallback(body, quarter, metric):
    """LLM 兜底：对正则漏抽的指标，用 LLM 抽取；数值必须原文正则验证，否则丢弃。"""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
        unit_map = {"per_premium": "件/亿元", "per_policy": "件/万张", "per_person": "件/万人次"}
        unit = unit_map.get(metric, "件")
        prompt = (f"从下面保险消费投诉通报正文中，抽取'{metric}'指标下被点名的公司及数值。"
                  f"只返回 JSON 数组 [{{\"company\":\"公司名\",\"value\":数值}}]，数值不带单位。正文:\n{body[:4000]}")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0, response_format={"type": "json_object"},
        )
        out = json.loads(resp.choices[0].message.content)
        items = out if isinstance(out, list) else out.get("data", out.get("items", []))
    except Exception as e:
        print(f"  [LLM兜底失败] {quarter}/{metric}: {e}")
        return []

    verified = []
    for it in items:
        comp = str(it.get("company", "")).strip()
        val = it.get("value")
        if not comp or not is_valid_company(comp) or val is None:
            continue
        # 数值原文验证：在正文中能找到"公司名...value...单位"
        pat = re.compile(re.escape(comp) + r"[^。]{0,15}?" + re.escape(str(val)) + r"\s*" + re.escape(unit))
        if pat.search(body):
            verified.append({"quarter": quarter, "company": comp,
                             "company_type": guess_type(comp), "metric": metric,
                             "value": float(val), "unit": unit, "_src": "llm_verified"})
    return verified


with open(BODIES, encoding="utf-8") as f:
    data = json.load(f)

all_records = []
fallback_log = []
for item in data:
    if "error" in item or not item.get("is_insurance"):
        continue
    q, body = item["quarter"], item["body"]
    recs, hits = regex_extract(body, q)
    all_records.extend(recs)
    # 完整度校验 + LLM 兜底
    for metric in EXPECTED_METRICS:
        if hits.get(metric, 0) == 0:
            print(f"  [正则为0→LLM兜底] {q}/{metric}")
            extra = llm_fallback(body, q, metric)
            fallback_log.append({"quarter": q, "metric": metric, "llm_count": len(extra)})
            all_records.extend(extra)

os.makedirs(os.path.dirname(DB), exist_ok=True)
con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("DROP TABLE IF EXISTS complaints")
cur.execute("""CREATE TABLE complaints (
    quarter TEXT, company TEXT, company_type TEXT, metric TEXT, value REAL, unit TEXT,
    PRIMARY KEY (quarter, company, metric, unit))""")
cur.executemany("INSERT OR REPLACE INTO complaints VALUES (?,?,?,?,?,?)",
                [(r["quarter"], r["company"], r["company_type"], r["metric"], r["value"], r["unit"])
                 for r in all_records])
con.commit()

print("total records:", len(all_records))
print("by quarter:", dict(Counter(r["quarter"] for r in all_records)))
print("by metric:", dict(Counter(r["metric"] for r in all_records)))
print("by type:", dict(Counter(r["company_type"] for r in all_records)))
print("llm fallback triggered:", len(fallback_log), fallback_log if fallback_log else "(none, 正则全覆盖)")

print("\n-- 2023Q1 核查 --")
for kc, km, kv in [("复星联合健康", "per_premium", 19.20), ("平安人寿", "per_premium", 2.11),
                   ("复星联合健康", "per_policy", 0.71), ("渤海人寿", "per_person", 0.56),
                   ("平安人寿", "complaint_count", 3625)]:
    row = cur.execute("SELECT value FROM complaints WHERE quarter='2023Q1' AND company=? AND metric=?",
                      (kc, km)).fetchone()
    status = "OK" if row and abs(row[0] - kv) < 0.01 else "MISMATCH"
    print(f"  {kc}/{km}: got={row[0] if row else None} expect={kv} [{status}]")
con.close()
