# PIPEUNCLE Scraper — 茄营 / 华盛 / 花店 烟丝数据

爬取三个渠道的手卷烟丝及耗材产品信息，生成价格对比表。

| 渠道 | 网站 | 价格单位 | 手卷丝 | 耗材 |
|------|------|----------|:-----:|:---:|
| 茄营 | [pipeuncle.com](https://www.pipeuncle.com) | USD | 102 款 | — |
| 华盛 | [huashengyansi.cv](https://www.huashengyansi.cv) | CNY 分 | 241 款 | 142 款 |
| 花店 | 日本烟渠道 | JPY | 189 款 | — |
| **合计** | | | **532 款** | **142 款** |

---

## 文件结构

### 爬虫脚本

| 文件 | 说明 |
|------|------|
| `decrypt.py` | 茄营 API 解密模块（AES-ECB） |
| `scrape_hand_rolled.py` | 爬取茄营手卷烟丝 |
| `scrape_all_except_hand_rolled.py` | 爬取茄营其他品类（雪茄/烟斗丝等） |
| `scrape_huashengyansi.py` | 爬取华盛全站产品 |
| `scrape_ribenyan.py` | 爬取花店（日本烟）数据 |

### 源数据（JSON）

| 文件 | 渠道 | 说明 |
|------|------|------|
| `pipeuncle_cigarette.json` | 茄营 | 手卷烟丝原始爬取数据 |
| `pipeuncle_cigarette_live.json` | 茄营 | 实时 API 价格（sellPrice） |
| `huasheng_products.json` | 华盛 | 全站产品原始爬取数据 |
| `ribenyan_products.json` | 花店 | 全站产品原始爬取数据 |

### 生成表格（CSV）

#### 手卷烟丝

| 文件 | 渠道 | 行数 | 说明 |
|------|------|:--:|------|
| **`all_cigarette.csv`** | 全渠道 | 532 | **全渠道汇总** |
| `pipeuncle_cigarette.csv` | 茄营 | 102 | 茄营单独 |
| `huasheng_cigarette.csv` | 华盛 | 241 | 华盛单独 |

**表头**：
```
渠道 | 产品名称 | 品牌 | 口味 | 不加税价格(¥) | 单包含税价(¥) | 美元价格($) |
毛重(g) | 运费(¥) | 价格/500g(¥) |
平摊运费(¥/包) | 平摊运费后烟丝成本/20支 | 20支成品烟价(¥) | 规格(g) | 库存 | 分类
```

#### 耗材（滤嘴/卷纸/空管等）

| 文件 | 渠道 | 行数 | 说明 |
|------|------|:--:|------|
| **`all_consumables.csv`** | 华盛 | 142 | 全渠道汇总 |
| `huasheng_consumables.csv` | 华盛 | 142 | 华盛单独 |

> 茄营、花店暂无耗材数据。

**表头**：
```
渠道 | 产品名称 | 不加税价格(¥) | 含税价格(¥) | 美元价格($) | 库存 | 分类
```

#### 辅助分析表

| 文件 | 说明 |
|------|------|
| `pipeuncle_shopping_plan.csv` | 推荐购物方案（超 1.5kg 免邮） |
| `pipeuncle_combo_vs_individual.csv` | 33 包组合 vs 单买价格对比 |
| `pipeuncle_recommended_picks.csv` | 每品牌不出错经典款推荐 |
| `pipeuncle_cigarette_raw.csv` | 茄营手卷丝 CSV 原始导出 |
| `huasheng_products.csv` | 华盛产品 CSV 原始导出 |
| `ribenyan_products.csv` | 花店产品 CSV 原始导出 |

---

## 计算公式

### 基础参数

| 参数 | 值 | 说明 |
|------|-----|------|
| USD/CNY | 6.79 | 美元兑人民币 |
| USD/JPY | 145.0 | 美元兑日元 |
| JPY/CNY | 0.0468 | 日元兑人民币（由上面两个推导） |
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
# 重新爬取各渠道
python3 scrape_hand_rolled.py       # 茄营手卷丝
python3 scrape_huashengyansi.py     # 华盛全站
python3 scrape_ribenyan.py          # 花店全站

# 生成全渠道汇总表（需先爬取源数据）
python3 << 'EOF'
import json, csv, re
# 加载三个渠道 JSON，按公式计算，输出 all_cigarette.csv
EOF
```
