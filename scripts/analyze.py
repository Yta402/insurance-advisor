"""投诉通报 SQL 分析：跑出真实洞察，输出 Markdown 报告。"""
import sqlite3

con = sqlite3.connect("insurance/data/complaints.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
lines = []
def w(s=""):
    lines.append(s)

w("# 保险公司服务质量数据分析报告")
w("> 数据源：金融监管总局保险消费投诉情况通报（2022Q3、2022Q4、2023Q1）")
w("> 定位：决策辅助——客观呈现，不构成投保建议")
w()

w("## 洞察1：人身险公司「亿元保费投诉量」排名 2023Q1（越高=服务质量越差）")
w("| 排名 | 公司 | 亿元保费投诉量(件/亿元) |")
w("|---|---|---|")
rows = cur.execute("""SELECT company, value FROM complaints
    WHERE quarter='2023Q1' AND metric='per_premium' AND company_type='人身险'
    ORDER BY value DESC LIMIT 12""").fetchall()
for i, r in enumerate(rows, 1):
    w(f"| {i} | {r['company']} | {r['value']} |")
w()

w("## 洞察2：健康险公司投诉率趋势（消费者买医疗/重疾险常接触的公司）")
w("这些公司正是健康保障类产品的主要供给方，其服务质量直接影响投保决策。")
w()
health = ["复星联合健康", "太平洋健康", "人保健康", "平安养老", "太平养老", "昆仑健康", "和谐健康"]
w("| 公司 | 2022Q3 | 2022Q4 | 2023Q1 | 趋势 |")
w("|---|---|---|---|---|")
for c in health:
    vals = {}
    for q in ["2022Q3", "2022Q4", "2023Q1"]:
        row = cur.execute("SELECT value FROM complaints WHERE company=? AND metric='per_premium' AND quarter=?", (c, q)).fetchone()
        vals[q] = row["value"] if row else None
    cells = [f"{vals[q]}" if vals[q] is not None else "—" for q in ["2022Q3", "2022Q4", "2023Q1"]]
    avail = [v for v in vals.values() if v is not None]
    if len(avail) >= 2:
        trend = "↑恶化" if avail[-1] > avail[0] else ("↓改善" if avail[-1] < avail[0] else "→持平")
    else:
        trend = "数据不足"
    w(f"| {c} | {cells[0]} | {cells[1]} | {cells[2]} | {trend} |")
w()

w("## 洞察3：人身险 vs 财险 整体服务质量对比（万张保单投诉量中位水平）")
w("| 公司类型 | 2023Q1 万张保单投诉量(件/万张) 样本均值 |")
w("|---|---|")
for ct in ["人身险", "财险"]:
    row = cur.execute("SELECT AVG(value) as avg FROM complaints WHERE metric='per_policy' AND company_type=? AND quarter='2023Q1'", (ct,)).fetchone()
    w(f"| {ct} | {round(row['avg'],3) if row['avg'] else '—'} |")
w()

w("## 洞察4：持续高投诉率的人身险公司（3个季度均上榜亿元保费投诉量）")
qcols = {}
for q in ["2022Q3", "2022Q4", "2023Q1"]:
    rs = cur.execute("SELECT company FROM complaints WHERE quarter=? AND metric='per_premium' AND company_type='人身险'", (q,)).fetchall()
    qcols[q] = set(r["company"] for r in rs)
persist = qcols["2022Q3"] & qcols["2022Q4"] & qcols["2023Q1"]
w(f"3 个季度均在「亿元保费投诉量较高」名单的人身险公司（共 {len(persist)} 家）：")
for c in sorted(persist):
    vals = []
    for q in ["2022Q3", "2022Q4", "2023Q1"]:
        row = cur.execute("SELECT value FROM complaints WHERE company=? AND metric='per_premium' AND quarter=?", (c, q)).fetchone()
        vals.append(f"{row['value']}" if row else "—")
    w(f"- **{c}**: {vals[0]} → {vals[1]} → {vals[2]} 件/亿元")
w()
w("---")
w("*本报告基于公开监管数据，仅作信息呈现，不构成投保建议。*")

report = "\n".join(lines)
with open("insurance/data/analysis_report.md", "w", encoding="utf-8") as f:
    f.write(report)
con.close()
print("report written, length:", len(report))
