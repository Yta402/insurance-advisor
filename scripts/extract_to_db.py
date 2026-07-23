"""从通报正文抽取结构化数据(公司×指标×季度)并入库 SQLite。"""
import json
import os
import re
import sqlite3

BODIES = "insurance/scripts/quarterly_bodies.json"
DB = "insurance/data/complaints.db"

with open(BODIES, encoding="utf-8") as f:
    data = json.load(f)

RATE_PATTERNS = [
    ("per_premium", "件/亿元", re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+\.\d+)件/亿元")),
    ("per_policy", "件/万张", re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+\.\d+)件/万张")),
    ("per_person", "件/万人次", re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+\.\d+)件/万人次")),
]

COUNT_SEG = re.compile(r"投诉量较[多高]的(财产保险公司|人身保险公司)为[:：]([^。]*)")
COUNT_ITEM = re.compile(r"([\u4e00-\u9fa5·]{2,12})(\d+)件")


def guess_type(name):
    if any(k in name for k in ["人寿", "健康", "养老", "生命", "年金"]):
        return "人身险"
    if any(k in name for k in ["财险", "农险", "财产", "相互", "在线", "车险",
                                "信保", "责任", "航运", "建工"]):
        return "财险"
    if "保险" in name:
        return "财险"
    return "未知"


NOISE = ["投诉量", "中位数", "保费", "亿元", "万张", "万人次", "较高", "较多",
         "为", "情况", "占", "的"]


def is_valid_company(name):
    """过滤正则误匹配的噪声(如'中位数为''投诉量较高'等被当公司名)。"""
    if not (2 <= len(name) <= 10):
        return False
    return not any(w in name for w in NOISE)


records = []
for item in data:
    if "error" in item or not item.get("is_insurance"):
        continue
    q = item["quarter"]
    body = item["body"]
    seen = set()
    for metric, unit, pat in RATE_PATTERNS:
        for m in pat.finditer(body):
            comp = m.group(1).strip()
            if not is_valid_company(comp):
                continue
            val = float(m.group(2))
            ctype = guess_type(comp)
            key = (q, comp, metric)
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "quarter": q, "company": comp, "company_type": ctype,
                "metric": metric, "value": val, "unit": unit,
            })
    for m in COUNT_SEG.finditer(body):
        ctype = "财险" if "财产" in m.group(1) else "人身险"
        seg = m.group(2)
        for mm in COUNT_ITEM.finditer(seg):
            comp = mm.group(1).strip()
            if not is_valid_company(comp):
                continue
            val = int(mm.group(2))
            key = (q, comp, "complaint_count")
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "quarter": q, "company": comp, "company_type": ctype,
                "metric": "complaint_count", "value": val, "unit": "件",
            })

os.makedirs(os.path.dirname(DB), exist_ok=True)
con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("DROP TABLE IF EXISTS complaints")
cur.execute(
    """CREATE TABLE complaints (
        quarter TEXT, company TEXT, company_type TEXT,
        metric TEXT, value REAL, unit TEXT,
        PRIMARY KEY (quarter, company, metric, unit)
    )"""
)
cur.executemany(
    "INSERT OR REPLACE INTO complaints VALUES (?,?,?,?,?,?)",
    [(r["quarter"], r["company"], r["company_type"], r["metric"], r["value"], r["unit"]) for r in records],
)
con.commit()

print("total records:", len(records))
from collections import Counter
print("by quarter:", dict(Counter(r["quarter"] for r in records)))
print("by metric:", dict(Counter(r["metric"] for r in records)))
print("by type:", dict(Counter(r["company_type"] for r in records)))

# 核查 2023Q1 已知数据点
print("\n-- 2023Q1 核查 --")
for known_company, known_metric, known_val in [
    ("复星联合健康", "per_premium", 19.20),
    ("平安人寿", "per_premium", 2.11),
    ("复星联合健康", "per_policy", 0.71),
    ("渤海人寿", "per_person", 0.56),
    ("平安人寿", "complaint_count", 3625),
]:
    row = cur.execute(
        "SELECT value FROM complaints WHERE quarter='2023Q1' AND company=? AND metric=?",
        (known_company, known_metric),
    ).fetchone()
    status = "OK" if row and abs(row[0] - known_val) < 0.01 else "MISMATCH"
    print(f"  {known_company}/{known_metric}: got={row[0] if row else None} expect={known_val} [{status}]")
con.close()
