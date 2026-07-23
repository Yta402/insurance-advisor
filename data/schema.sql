-- Insurance 项目数据模型 Schema
-- 状态标注：[已实现] / [待采集] / [AI生成]

-- ============ 1. 投诉服务质量数据 [已实现] ============
-- 来源：金融监管总局保险消费投诉情况通报
-- 局限：通报仅列"投诉较高"的前若干家公司，非全市场
CREATE TABLE IF NOT EXISTS complaints (
    quarter         TEXT,           -- 季度，如 '2023Q1'
    company         TEXT,           -- 保险公司
    company_type    TEXT,           -- 人身险/财险/未知
    metric          TEXT,           -- complaint_count/per_premium/per_policy/per_person
    value           REAL,           -- 数值
    unit            TEXT,           -- 件/件每亿元/件每万张/件每万人次
    PRIMARY KEY (quarter, company, metric, unit)
);

-- ============ 2. 保险产品库 [待采集] ============
-- 来源：各保险公司官网"公开信息披露"（监管强制披露条款+费率表）
-- 注意：行业协会 icidp 声明禁止数据提取，改走各公司官网
CREATE TABLE IF NOT EXISTS products (
    product_id      TEXT PRIMARY KEY,
    product_name    TEXT,           -- 产品名称
    company         TEXT,           -- 所属公司（可与 complaints.company 关联）
    insurance_type  TEXT,           -- 重疾/医疗/意外
    form            TEXT,           -- 消费型/储蓄型/返还型
    sum_insured     TEXT,           -- 保额档位
    premium_sample  TEXT,           -- 示例保费（30岁男50万，待采集）
    key_features    TEXT,           -- 关键条款要点（重疾分组/中轻症/癌症多次赔等）
    health_notice   TEXT,           -- 健康告知宽松度（粗粒度提示，非核保判断）
    source_url      TEXT,
    data_version    TEXT,           -- 数据版本/采集日期
);

-- ============ 3. 用户画像 [AI 输入] ============
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id      TEXT PRIMARY KEY,
    age             INTEGER,
    income          TEXT,           -- 低/中/中高/高
    family          TEXT,           -- 家庭结构
    health          TEXT,           -- 健康粗粒度（健康/亚健康/有慢性病）——仅适配提示，非核保
    budget          TEXT,           -- 年预算
);

-- ============ 4. AI 匹配结果 [AI 生成] ============
CREATE TABLE IF NOT EXISTS recommendations (
    profile_id      TEXT,
    insurance_type  TEXT,           -- 推荐险种
    form            TEXT,
    reason          TEXT,
    sum_insured_range TEXT,
    priority        TEXT,           -- 高/中
    annual_budget   TEXT,
    notes           TEXT,           -- 合规与个性化提示
    PRIMARY KEY (profile_id, insurance_type)
);

-- 关联关系：recommendations.insurance_type -> products.insurance_type -> products.company -> complaints.company
-- 即：用户画像 -> AI推荐险种 -> 该险种产品 -> 产品所属公司的服务质量(投诉)数据
-- 体现"产品匹配 + 公司服务质量"双维度决策辅助

-- ============ 采集状态备忘 ============
-- complaints: 已采集 3 季度(2022Q3/Q4/2023Q1)，169 条；季度扩充受限于官网检索
-- products:   待采集；各公司官网分散，格式不一，工作量大；优先采重疾险(含返还型/小姨案例)
-- 局限诚实标注：complaints 非全市场(仅投诉较高名单)；products 待补全
