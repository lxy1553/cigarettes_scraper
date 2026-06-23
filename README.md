# Cigarettes Scraper — 手卷烟丝 & 耗材数据采集与价格对比

爬取 5 个渠道的手卷烟丝、成品烟、烟斗丝及耗材产品信息，统一数据模型，生成价格对比分析。

| 渠道 | 简称 | 网站 | 价格原始单位 | 产品大类 |
|------|------|------|:----------:|---------|
| 华盛 | huasheng | [huashengyansi.cv](https://www.huashengyansi.cv) | CNY(分) | 手卷丝 / 耗材 / 成品烟 / 加热烟弹 |
| 茄营 | pipeuncle | [pipeuncle.com](https://www.pipeuncle.com) | USD | 手卷丝 |
| 花店 | ribenyan | [ribenyan.com](https://ribenyan.com) | JPY | 成品烟 / 手卷丝 / 雪茄 / 烟斗丝 |
| — | nov | [novapipesandtobacco.com](https://novapipesandtobacco.com) | USD | 烟斗丝(散装) |
| — | sp | 参考数据 | USD | 烟斗丝(罐装) |

---

## 数据分层

```
data/
├── ods/                          # 原始数据（5渠道，不动）
│   ├── pipeuncle_products.json
│   ├── huasheng_products.json
│   ├── ribenyan_products.json
│   ├── nov_products.json
│   ├── sp_products.json
│   └── *products.csv（JSON的CSV镜像，数组已展开）
│
├── dwd/                          # 明细数据（统一20字段模型）
│   ├── product_detail.json        1471行
│   ├── product_detail.csv         ← 主要分析表
│   └── field_mapping.csv          字段对照表
│
├── dws/                          # 汇总数据
│   ├── channel_overview.csv       各渠道概览
│   ├── price_by_brand.csv         按品牌价格对比（235品牌）
│   ├── price_by_type.csv          按产品大类汇总（9类）
│   ├── price_by_weight_range.csv  按重量段分布
│   ├── all_cigarette.csv          全渠道手卷烟丝（含计算字段）
│   └── all_consumables.csv        全渠道耗材
│
└── ads/                          # 应用层
    ├── products.json              通用产品数据
    ├── products_by_type.json      按大类分组
    ├── web_products.json          （前端）
    ├── web_consumables.json       （前端）
    ├── web_cigarette.json         （前端）
    └── field_reference.json       （前端）

scripts/
├── build_dwd.py                  # ODS → DWD（含品牌/口味提取）
└── build_dws_ads.py              # DWD → DWS + ADS
```

---

## DWD 字段对照表（20字段）

| # | 字段 | 填充率 | 说明 |
|---|------|:-----:|------|
| 1 | 渠道 | 100% | 数据来源：huasheng/pipeuncle/ribenyan/nov/sp |
| 2 | 库存编码 | 37% | 唯一 SKU |
| 3 | 产品名称 | 100% | 产品完整名称 |
| 4 | 品牌 | 100% | 自动提取，235品牌 |
| 5 | 分类 | 99% | 原渠道分类路径 |
| 6 | 产品大类 | 100% | 手卷丝/成品烟/烟斗丝/雪茄/耗材/加热烟弹/套餐/烟丝/其他 |
| 7 | 原始价格 | 100% | 原始币种价格 |
| 8 | 原始币种 | 100% | USD/CNY/JPY |
| 9 | 美元价格 | 100% | 统一换算为美元 |
| 10 | 人民币价格 | 100% | 统一换算为人民币 |
| 11 | 重量(克) | 100% | 单规格净重 |
| 12 | 规格 | 44% | 规格描述 |
| 13 | 是否有货 | 100% | 库存状态 |
| 14 | 库存数量 | 100% | 库存余量 |
| 15 | 成分 | 3% | 烟草配方（仅pipeuncle有） |
| 16 | 切工 | 4% | 烟丝切工（仅pipeuncle有） |
| 17 | 劲道 | 3% | 浓度等级（仅pipeuncle有） |
| 18 | 口味 | 34% | 从产品名提取的风味描述 |
| 19 | 商品链接 | 86% | 详情页URL |
| 20 | 原始ID | 100% | 来源系统ID |

详见 `data/dwd/field_mapping.csv`

---

## 计算公式

### 基础参数

| 参数 | 值 | 说明 |
|------|-----|------|
| USD/CNY | 6.79 | 美元兑人民币 |
| USD/JPY | 145.0 | 美元兑日元 |
| JPY/CNY | 0.0468 | 日元兑人民币 |
| 税费 | ×1.5 | 从价税 50% |
| 运费 | ¥160/kg | 首重 1kg（华盛/花店烟丝） |
| 运费(耗材) | ¥98/kg | 首重 1kg（华盛耗材） |
| 茄营运费 | 0 | 满 1.5kg 免邮 |
| 每支用丝量 | 待确认 | 见下方说明 |

### 各渠道价格处理

```
茄营:   商品价格¥ = price_rmb（爬取）
华盛:   商品价格¥ = price ÷ 100（分→元）
花店:   商品价格¥ = price × 0.0468（JPY→CNY）
nov:    商品价格¥ = price_usd × 6.79（USD→CNY）
sp:     商品价格¥ = price_usd × 6.79（USD→CNY）
```

### 计算字段公式

```
含税价¥       = 商品价格¥ × 1.5
美元价格$     = 商品价格¥ ÷ 6.79
克单价        = 含税价¥ ÷ 规格g
500g单价     = (500 ÷ 规格g) × 含税价¥
```

### 20支成本计算

用 **70mm 卷烟纸 + 6×30mm 滤嘴**，每支填充段约 40mm。

| 参数 | 值 | 说明 |
|------|-----|------|
| 每支用丝量 | 0.6g | 细支(6mm)，正常填充密度 |
| 20支用丝量 | 12g | — |
| 耗材成本(纸+滤嘴) | ¥0.195/支 | 约 ¥3.90/20支套 |

```
每支烟丝成本   = 0.6g × 克单价
20支烟丝成本  = 12g × 克单价
20支成品成本  = 20支烟丝成本 + 每支耗材成本 × 20
```

---

## 使用

```bash
# 完整重建
python3 scripts/build_dwd.py              # ODS → DWD
python3 scripts/build_dws_ads.py          # DWD → DWS + ADS

# 或单步重建
# 爬取各渠道
python3 scripts/pipeuncle/scrape_hand_rolled.py
python3 scripts/huasheng/scrape_huashengyansi.py
python3 scripts/ribenyan/scrape_ribenyan.py
python3 scripts/nov/scrape_nov.py
```
