# Cigarettes Scraper — 手卷烟丝 & 耗材数据采集与价格对比

爬取三个渠道的手卷烟丝、成品烟及耗材产品信息，计算含税价、运费分摊、单支成本，生成价格对比表。

| 渠道 | 网站 | 价格单位 | 产品数 | 耗材数 |
|------|------|----------|:------:|:------:|
| 茄营 | [pipeuncle.com](https://www.pipeuncle.com) | USD | 102+ | — |
| 华盛 | [huashengyansi.cv](https://www.huashengyansi.cv) | CNY 分 | 241 | 142 |
| 花店 | [ribenyan.com](https://ribenyan.com) | JPY | 189 | — |
| **合计** | | | **532+** | **142** |

---

## 项目结构

```
├── README.md
├── .gitignore
├── index.html                        # 浏览器端数据看板
├── scripts/
│   ├── pipeuncle/
│   │   ├── scrape_hand_rolled.py              # 爬取茄营手卷烟丝
│   │   └── scrape_all_except_hand_rolled.py   # 爬取茄营其他品类
│   ├── huasheng/
│   │   └── scrape_huashengyansi.py            # 爬取华盛全站
│   ├── ribenyan/
│   │   └── scrape_ribenyan.py                 # 爬取花店（日本烟）
│   └── utils/
│       └── decrypt.py                         # AES-ECB 解密模块
├── data/
│   ├── pipeuncle/                             # 茄营数据
│   │   ├── cigarette.json                     # 手卷烟丝原始爬取
│   │   ├── cigarette_raw.csv                  # 同上 CSV 原始导出
│   │   ├── cigarette_live.json                # 实时 API 价格
│   │   ├── cigarette.csv                      # 茄营单独处理表
│   │   ├── combo_vs_individual.csv            # 组合 vs 单买对比
│   │   ├── recommended_picks.csv              # 每品牌经典款推荐
│   │   └── shopping_plan.csv                  # 推荐购物方案
│   ├── huasheng/                              # 华盛数据
│   │   ├── products.json                      # 全站产品原始爬取
│   │   ├── products.csv                       # 全站 CSV 原始导出
│   │   ├── cigarette.csv                      # 华盛手卷烟丝
│   │   └── consumables.csv                    # 华盛耗材
│   ├── ribenyan/                              # 花店数据
│   │   ├── products.json                      # 全站产品原始爬取
│   │   └── products.csv                       # 全站 CSV 原始导出
│   └── aggregated/                            # 汇总表
│       ├── all_cigarette.csv                  # 全渠道手卷烟丝汇总
│       ├── all_consumables.csv                # 全渠道耗材汇总
│       ├── web_products.json                  # 前端用全渠道产品
│       └── web_consumables.json               # 前端用全渠道耗材
└── assets/
    └── e6d0d2b769ebdd436389877f7819b703.jpg
```

---

## 数据说明

### 手卷烟丝

**表头**：`渠道 | 产品名称 | 品牌 | 口味 | 不加税价格(¥) | 单包含税价(¥) | 美元价格($) | 毛重(g) | 运费(¥) | 价格/500g(¥) | 平摊运费(¥/包) | 平摊运费后烟丝成本/20支 | 20支成品烟价(¥) | 规格(g) | 库存 | 分类`

| 文件 | 渠道 | 行数 | 说明 |
|------|------|:----:|------|
| `data/aggregated/all_cigarette.csv` | 全渠道 | 532 | **全渠道汇总** |
| `data/pipeuncle/cigarette.csv` | 茄营 | 102 | 茄营单独 |
| `data/huasheng/cigarette.csv` | 华盛 | 241 | 华盛单独 |

### 耗材

**表头**：`渠道 | 产品名称 | 不加税价格(¥) | 含税价格(¥) | 美元价格($) | 库存 | 分类`

| 文件 | 渠道 | 行数 | 说明 |
|------|------|:----:|------|
| `data/aggregated/all_consumables.csv` | 华盛 | 142 | 全渠道汇总 |
| `data/huasheng/consumables.csv` | 华盛 | 142 | 华盛单独 |

> 茄营、花店暂无耗材数据。

### 辅助分析表（`data/pipeuncle/`）

| 文件 | 说明 |
|------|------|
| `shopping_plan.csv` | 推荐购物方案（超 1.5kg 免邮） |
| `combo_vs_individual.csv` | 组合包 vs 单买价格对比 |
| `recommended_picks.csv` | 每品牌不出错经典款推荐 |

---

## 计算公式

### 基础参数

| 参数 | 值 | 说明 |
|------|-----|------|
| USD/CNY | 6.79 | 美元兑人民币 |
| USD/JPY | 145.0 | 美元兑日元 |
| JPY/CNY | 0.0468 | 日元兑人民币 |
| 税费 | ×1.5 | 从价税 50% |
| 茄营运费 | 0 | 满 1.5kg（毛重）免邮 |
| 华盛/花店烟丝运费 | ¥160/kg | 首重 1kg |
| 华盛耗材运费 | ¥98/kg | 首重 1kg |
| 耗材成本 | ¥3.90 | 20 支纸+滤嘴 |
| 每支用丝量 | 0.7g | 20 支 = 14g |

### 各渠道价格处理

```
茄营:   售价 = price_rmb（爬取）   →  含税价 = 售价 × 1.5
华盛:   售价 = price ÷ 100（分→元） →  含税价 = 售价 × 1.5
花店:   售价 = price × 0.0468（JPY→CNY）→  含税价 = 售价 × 1.5
```

### 字段公式

```
单包含税价     = 售价 × 1.5
美元价格       = 售价(¥) ÷ 6.79
价格/500g      = (500 ÷ 规格g) × 含税价
平摊运费       = 毛重g ÷ 1000 × 运费单价(¥/kg)
烟丝成本/20支   = (14g ÷ 规格g) × 含税价 + 14g × 运费单价
20支成品烟价   = 烟丝成本 + ¥3.90 + 耗材平摊运费
```

---

## 使用

```bash
# 定位到项目根目录
cd cigarettes_scraper

# 重新爬取各渠道
python3 scripts/pipeuncle/scrape_hand_rolled.py              # 茄营手卷丝
python3 scripts/pipeuncle/scrape_all_except_hand_rolled.py   # 茄营其他品类
python3 scripts/huasheng/scrape_huashengyansi.py             # 华盛全站
python3 scripts/ribenyan/scrape_ribenyan.py                  # 花店全站
```

脚本自动输出到对应的 `data/<渠道>/` 目录。
