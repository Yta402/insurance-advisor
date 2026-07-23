"""生成 Plotly 交互式 HTML 看板：保险公司服务质量数据分析。"""
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

con = sqlite3.connect("insurance/data/complaints.db")
df = pd.read_sql("SELECT * FROM complaints", con)
con.close()

RED, BLUE, ORANGE = "#d62728", "#1f77b4", "#ff7f0e"

# 图1：人身险亿元保费投诉量排名 2023Q1
d1 = df[(df["quarter"] == "2023Q1") & (df["metric"] == "per_premium")
        & (df["company_type"] == "人身险")].sort_values("value", ascending=True)
fig1 = go.Figure(go.Bar(x=d1["value"], y=d1["company"], orientation="h",
                        marker_color=RED, text=d1["value"], textposition="outside"))
fig1.update_layout(title="洞察1｜人身险公司「亿元保费投诉量」排名 2023Q1（越高=服务质量越差）",
                   xaxis_title="件/亿元", height=480, margin=dict(l=10, r=60))

# 图2：健康险公司投诉率趋势
health = ["复星联合健康", "太平洋健康", "人保健康", "平安养老", "太平养老", "昆仑健康", "和谐健康"]
d2 = df[(df["company"].isin(health)) & (df["metric"] == "per_premium")]
fig2 = go.Figure()
for c in health:
    sub = d2[d2["company"] == c].sort_values("quarter")
    if len(sub):
        fig2.add_trace(go.Scatter(x=sub["quarter"], y=sub["value"],
                                  mode="lines+markers+text", name=c,
                                  text=sub["value"], textposition="top center"))
fig2.update_layout(title="洞察2｜健康险公司 亿元保费投诉量趋势（消费者买医疗/重疾险常接触）",
                   xaxis_title="季度", yaxis_title="件/亿元", height=460,
                   legend=dict(orientation="h", y=-0.2))

# 图3：人身险 vs 财险
d3 = df[(df["quarter"] == "2023Q1") & (df["metric"] == "per_policy")] \
    .groupby("company_type")["value"].mean().reset_index()
fig3 = go.Figure(go.Bar(x=d3["company_type"], y=d3["value"],
                        marker_color=[BLUE, ORANGE],
                        text=[round(v, 2) for v in d3["value"]], textposition="outside"))
fig3.update_layout(title="洞察3｜人身险 vs 财险 万张保单投诉量均值 2023Q1（财险投诉率显著更高）",
                   yaxis_title="件/万张", height=400, showlegend=False)

# 图4：2023Q1 人身险 万张保单投诉量排名
d4 = df[(df["quarter"] == "2023Q1") & (df["metric"] == "per_policy")
        & (df["company_type"] == "人身险")].sort_values("value", ascending=True)
fig4 = go.Figure(go.Bar(x=d4["value"], y=d4["company"], orientation="h",
                        marker_color="#9467bd", text=d4["value"], textposition="outside"))
fig4.update_layout(title="洞察4｜人身险公司「万张保单投诉量」排名 2023Q1",
                   xaxis_title="件/万张", height=420, margin=dict(l=10, r=60))

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>保险公司服务质量数据分析看板</title></head>
<body style="font-family:'Microsoft YaHei',sans-serif;max-width:1100px;margin:auto;padding:20px">
<h1>保险公司服务质量数据分析看板</h1>
<p><b>数据源</b>：金融监管总局保险消费投诉情况通报（2022Q3/2022Q4/2023Q1）｜
<b>定位</b>：决策辅助，客观呈现，不构成投保建议</p>
<hr>
{pio.to_html(fig1, include_plotlyjs='cdn', full_html=False)}
{pio.to_html(fig2, include_plotlyjs=False, full_html=False)}
{pio.to_html(fig3, include_plotlyjs=False, full_html=False)}
{pio.to_html(fig4, include_plotlyjs=False, full_html=False)}
<hr>
<p style="color:#666;font-size:13px">本看板基于公开监管数据，仅作信息呈现。通报仅列"投诉较高"的前若干家公司，
非全市场；"未上榜"不等于"无投诉"。</p>
</body></html>"""

with open("insurance/data/dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)
print("dashboard.html written | figures: 4 | records:", len(df))
