"""
数据聚合脚本：将各渠道原始数据合并为 all_cigarette.csv 和 all_consumables.csv
运行方式: python3 scripts/aggregate.py
"""
import csv
import json
import os
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

CIGARETTE_COLS = [
    '渠道', '产品名称', '品牌', '口味',
    '不加税价格 (¥)', '单包含税价 (¥)', '美元价格 ($)',
    '毛重 (g)', '运费 (¥)',
    '价格/500g (¥)', '平摊运费 (¥/包)',
    '平摊运费后烟丝成本/20支', '20支成品烟价 (¥)',
    '规格 (g)', '库存', '分类'
]

CONSUMABLES_COLS = [
    '渠道', '品牌', '种类', '规格', '个数',
    '不加税价格 (¥)', '含税价格 (¥)', '美元价格 ($)',
    '库存', '口味/描述'
]

# 分类关键词
SHOUJUAN_KEYWORDS = [
    '手卷|', 'red field', '红场', '史丹利', 'stanley', '鼓', 'drum',
    '霍本', 'old holborn', 'gv', '巴西', 'brazil', '黑鹰', 'black hawk',
    '黑蜘蛛', 'black spider', '丰收', 'harvest', '小骏马', 'colts',
    '红牛', 'red bull', '切格瓦拉', 'che', '巴厘', 'bali shag',
    'stamp/special', 'shag', 'zware', 'rolling',
]

YANDOU_KEYWORDS = [
    '彼得森', 'peterson', 'sg', '丹.', '马坝', 'macbaren', 'mac baren',
    '拉特雷', 'rattray', '拉森', 'w.o.larsen', 'cd 康奈尔', 'cornell',
    '小皇家', 'royal', 'g.l.', 'gl pease', '飞机', 'stanislaw',
    '好味', 'taste', '皇家', 'ark royal', '罗伯特', '蝴蝶', 'butterfly',
    '登喜路', 'dunhill', '绞盘', 'capstan', '三修女', '圣布鲁诺',
    '长老', '威塞克斯', 'wessex', '黑船長', 'captain black',
    '帆船', 'borkum riff', '斯坦維爾', 'stanwell', '萨利',
    '加维', 'gawith', '萨缪尔', 'samuel', '康奈尔和迪尔', 'cornell & diehl',
    '大卫杜夫', 'davidoff', '法官', 'judge', 'orlik', '黑法官',
    '索兰尼', 'solani', 'hu', 'kopp', '沙芬', 'savinelli',
    'mo', 'glp', 'bison', '野牛', '水手', 'vanelle',
    '伊尔斯特德', 'ilsted', '查卡姆', 'charcom', 'kk', 'kohlhase',
    '温斯洛', 'winslow', '华云', 'vauen', '阿斯顿', 'ashton',
    '罗伯特麦康奈尔', 'robert mcconnell', '斗丝 |', '斗丝',
    'flake', 'mixture', 'latakia', 'navy', 'balkan', 'virginia blend',
    'pipe', '斗草', '烟斗',
]


def classify_product(channel, name, orig_cat):
    """统一分类逻辑"""
    name_lower = name.lower() if name else ''

    if channel == '茄营':
        return '手卷组合' if '组合' in orig_cat else '手卷（手卷丝）'

    if channel == 'ribenyan':
        cat_map = {'手卷': '手卷（手卷丝）', '烟斗丝': '烟斗（斗草）', '套餐': '手卷组合'}
        if orig_cat in cat_map:
            return cat_map[orig_cat]
        return '其他'  # 外国香烟/日本香烟/雪茄/烟丝等归为其他

    if '套餐' in name or '组合' in name:
        return '手卷组合'

    # 花店渠道：手卷|XXX → 手卷
    if channel == '花店':
        if orig_cat.startswith('手卷|'):
            return '手卷（手卷丝）'
        if orig_cat.startswith('烟丝|'):
            brand_part = orig_cat.replace('烟丝|', '').lower()
            for kw in YANDOU_KEYWORDS:
                if kw.lower() in brand_part:
                    return '烟斗（斗草）'
            return '手卷（手卷丝）'

    # 华盛渠道：按品牌关键词匹配
    for kw in YANDOU_KEYWORDS:
        if kw.lower() in orig_cat.lower() or kw.lower() in name_lower:
            return '烟斗（斗草）'

    for kw in SHOUJUAN_KEYWORDS:
        if kw.lower() in orig_cat.lower() or kw.lower() in name_lower:
            return '手卷（手卷丝）'

    return '其他'


def calculate_fields(row):
    """
    标准化计算公式，对所有行统一计算衍生字段。

    已知公式（已验证）:
      单包含税价 (¥) = 不加税价格 (¥) × 1.5          ← 税率 50%
      美元价格 ($)    = 不加税价格 (¥) ÷ 6.80         ← 汇率
      价格/500g (¥)  = 单包含税价 ÷ 规格(g) × 500   ← 标准化到500g

    估算公式:
      平摊运费 (¥/包) = 运费 × (毛重 ÷ 1500)         ← 满1.5kg免运费
      成本/20支       = (含税价 + 平摊运费) ÷ 规格 × 0.7 × 20
      成品价/20支     = (含税价 + 平摊运费) ÷ 规格 × 0.7 × 20 × 1.5
    """
    row = dict(row)  # work on copy

    # Parse numeric fields
    raw_price_untax = safe_float(row.get('不加税价格 (¥)', ''))
    raw_price_taxed = safe_float(row.get('单包含税价 (¥)', ''))
    raw_usd = safe_float(row.get('美元价格 ($)', ''))
    raw_shipping = safe_float(row.get('运费 (¥)', ''))
    raw_gross = safe_float(row.get('毛重 (g)', ''))
    raw_spec = safe_float(row.get('规格 (g)', ''))
    raw_avg_ship = safe_float(row.get('平摊运费 (¥/包)', ''))

    # ---- 1. 含税价 / 不加税价 互推 ----
    if raw_price_taxed <= 0 and raw_price_untax > 0:
        raw_price_taxed = round(raw_price_untax * 1.5, 2)
    if raw_price_untax <= 0 and raw_price_taxed > 0:
        raw_price_untax = round(raw_price_taxed / 1.5, 2)

    # ---- 2. 美元价格 ----
    if raw_usd <= 0 and raw_price_untax > 0:
        raw_usd = round(raw_price_untax / 6.80, 2)

    # ---- 3. 价格/500g (¥) ----
    price_per_500 = safe_float(row.get('价格/500g (¥)', ''))
    if price_per_500 <= 0 and raw_price_taxed > 0 and raw_spec > 0:
        price_per_500 = round(raw_price_taxed / raw_spec * 500, 2)

    # ---- 4. 平摊运费 (¥/包) ----
    shipping_per_pack = raw_avg_ship
    if shipping_per_pack <= 0 and raw_shipping > 0 and raw_gross > 0:
        shipping_per_pack = round(raw_shipping * raw_gross / 1500, 2)
        if shipping_per_pack > raw_shipping:
            shipping_per_pack = raw_shipping  # cap at full shipping
    if shipping_per_pack <= 0:
        shipping_per_pack = raw_shipping  # fallback to raw shipping

    # ---- 5. 平摊运费后烟丝成本/20支 ----
    cost_20 = safe_float(row.get('平摊运费后烟丝成本/20支', ''))
    if cost_20 <= 0 and raw_spec > 0 and raw_price_taxed > 0:
        cost_20 = round((raw_price_taxed + shipping_per_pack) / raw_spec * 0.7 * 20, 2)

    # ---- 6. 20支成品烟价 (¥) ----
    finish_20 = safe_float(row.get('20支成品烟价 (¥)', ''))
    if finish_20 <= 0 and cost_20 > 0:
        finish_20 = round(cost_20 * 1.5, 2)

    # Write back
    row['不加税价格 (¥)'] = str(raw_price_untax) if raw_price_untax > 0 else ''
    row['单包含税价 (¥)'] = str(raw_price_taxed) if raw_price_taxed > 0 else ''
    row['美元价格 ($)'] = str(raw_usd) if raw_usd > 0 else ''
    row['价格/500g (¥)'] = str(price_per_500) if price_per_500 > 0 else ''
    row['平摊运费 (¥/包)'] = str(shipping_per_pack) if shipping_per_pack > 0 else ''
    row['平摊运费后烟丝成本/20支'] = str(cost_20) if cost_20 > 0 else ''
    row['20支成品烟价 (¥)'] = str(finish_20) if finish_20 > 0 else ''

    return row


def safe_float(val):
    try:
        return float(str(val).strip().replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def read_csv(path):
    """读取 UTF-8 BOM CSV，返回行列表（OrderedDict）"""
    rows = []
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(OrderedDict((k.strip(), v.strip()) for k, v in row.items()))
    return rows


def write_csv(path, rows, fieldnames):
    """写入 UTF-8 BOM CSV"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"  → {path} ({len(rows)} 行)")


def aggregate_cigarette():
    """合并烟草产品数据"""
    all_rows = []
    seen = set()  # 去重

    # 1. 读取华盛数据
    huasheng_path = os.path.join(DATA_DIR, 'huasheng', 'cigarette.csv')
    if os.path.exists(huasheng_path):
        for row in read_csv(huasheng_path):
            key = (row.get('渠道', ''), row.get('产品名称', ''))
            if key not in seen:
                seen.add(key)
                row['分类'] = classify_product(row.get('渠道', ''), row.get('产品名称', ''), row.get('分类', ''))
                all_rows.append(calculate_fields(row))

    # 2. 读取 PipeUncle（茄营）数据
    pipeuncle_path = os.path.join(DATA_DIR, 'pipeuncle', 'cigarette.csv')
    if os.path.exists(pipeuncle_path):
        for row in read_csv(pipeuncle_path):
            key = (row.get('渠道', ''), row.get('产品名称', ''))
            if key not in seen:
                seen.add(key)
                row['分类'] = classify_product(row.get('渠道', ''), row.get('产品名称', ''), row.get('分类', ''))
                all_rows.append(calculate_fields(row))

    # 3. 读取 Ribenyan 数据
    ribenyan_path = os.path.join(DATA_DIR, 'ribenyan', 'products.csv')
    if os.path.exists(ribenyan_path):
        for row in read_csv(ribenyan_path):
            key = (row.get('渠道', ''), row.get('产品名称', ''))
            if key not in seen:
                seen.add(key)
                row['分类'] = classify_product(row.get('渠道', ''), row.get('产品名称', ''), row.get('分类', ''))
                all_rows.append(row)

    # 4. 写入
    output_path = os.path.join(DATA_DIR, 'aggregated', 'all_cigarette.csv')
    write_csv(output_path, all_rows, CIGARETTE_COLS)
    return len(all_rows)


def aggregate_consumables():
    """合并耗材数据"""
    all_rows = []
    seen = set()

    # 华盛耗材
    huasheng_path = os.path.join(DATA_DIR, 'huasheng', 'consumables.csv')
    if os.path.exists(huasheng_path):
        for row in read_csv(huasheng_path):
            # 使用口味/描述作为去重键（唯一标识产品）
            desc = row.get('口味/描述', '')
            brand = row.get('品牌', '')
            spec = row.get('规格', '')
            key = (brand, spec, desc[:30])
            if key not in seen:
                seen.add(key)
                clean = OrderedDict()
                for col in CONSUMABLES_COLS:
                    clean[col] = row.get(col, '')
                all_rows.append(clean)

    # 输出
    output_path = os.path.join(DATA_DIR, 'aggregated', 'all_consumables.csv')
    write_csv(output_path, all_rows, CONSUMABLES_COLS)
    return len(all_rows)


def generate_web_json():
    """为 index.html 生成嵌入的 JSON 备份（可选）"""
    import json

    cig_path = os.path.join(DATA_DIR, 'aggregated', 'all_cigarette.csv')
    cons_path = os.path.join(DATA_DIR, 'aggregated', 'all_consumables.csv')

    if os.path.exists(cig_path):
        rows = read_csv(cig_path)
        with open(os.path.join(DATA_DIR, 'aggregated', 'web_cigarette.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False)
        print(f"  → web_cigarette.json ({len(rows)} 行)")

    if os.path.exists(cons_path):
        rows = read_csv(cons_path)
        with open(os.path.join(DATA_DIR, 'aggregated', 'web_consumables.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False)
        print(f"  → web_consumables.json ({len(rows)} 行)")


if __name__ == '__main__':
    print("=" * 50)
    print("数据聚合脚本")
    print("=" * 50)

    print("\n[1/2] 合并烟草产品...")
    n = aggregate_cigarette()

    print(f"\n[2/2] 合并耗材...")
    m = aggregate_consumables()

    print("\n[可选] 生成 JSON 备份...")
    generate_web_json()

    print(f"\n{'=' * 50}")
    print(f"完成！烟草 {n} 条，耗材 {m} 条")
    print(f"{'=' * 50}")
