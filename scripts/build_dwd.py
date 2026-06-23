"""
Build DWD (Data Warehouse Detail) layer from ODS raw data.
Unifies all channel schemas into a common product_detail table with:
- Chinese field names
- Unified currency conversion (USD + CNY)
- Weight normalization (oz/kg → g)
- Variant expansion (one row per SKU)
- Product type classification (手卷丝/烟斗丝/成品烟/耗材/...)
- Brand extraction from product names
- Flavor extraction from product names
- Simplified Chinese conversion
"""
import json
import csv
import os
import re
from zhconv import convert

# ── 汇率 ──
USD_CNY = 6.79
USD_JPY = 145.0
JPY_CNY = 0.0468

def _cny_to_usd(cny): return round(cny / USD_CNY, 4)
def _usd_to_cny(usd): return round(usd * USD_CNY, 4)
def _jpy_to_cny(jpy): return round(jpy * JPY_CNY, 4)
def _jpy_to_usd(jpy): return round(jpy / USD_JPY, 4)

# ── 品牌词典（从各渠道收集，优先长匹对） ──

BRAND_DICT = sorted(set([
    # 已有品牌字段
    "7Seas", "7seas", "A&C Petersen", "AMPHORA", "APACHE",
    "Acrema Blend", "American Spirit", "Amsterdamer", "Amber Leaf",
    "AmericanSpirit", "Arango", "Ark Royal", "BORKUM RIFF",
    "BRIGHT", "Bali Shag", "Bali", "Balkan Sasieni", "Bentley",
    "Benson Hedges", "Bi Bo", "Bison", "Black Devil", "Black Hawk",
    "Black Jack", "Black Spider", "BlackDevil", "BlackJack", "Brebbana",
    "Brigham", "Buzz", "CHACOM", "Camel", "Capstan", "Captain Black",
    "Captain Earle", "Carter Hall", "Chacom", "Che", "Colts",
    "Comoy's", "Cornell & Diehl", "Cult", "DAN", "Dan", "Davidoff",
    "Drum", "Dunhill", "Erinmore", "Escudo", "F&K", "Falcon",
    "G.L. Pease", "G.L.", "GV", "Gawith Hoggarth", "Gizeh",
    "Golden Virginia", "HOT", "HU Tobacco", "Half & Half",
    "Harvest", "Heinrichs", "IM Corona", "KENT", "KK", "Kent",
    "Kool", "LD", "Lane Limited", "Lucky Strike", "Mac Baren",
    "Marie", "Marlboro", "Mascotte", "Mevius", "Missouri Meerschaum",
    "Nording", "OCB", "Old Holborn", "Orlik", "PALL MALL",
    "PS", "Parliament", "Peter Stokkebye", "Petersen", "Philip Morris",
    "Prince Albert", "Princeton", "Pure", "R+", "RAW", "RIZLA",
    "Red Bull", "Red Field", "Rizia", "Rizla", "Robert McConnell",
    "Rothmans", "Royal", "SG", "ST DUPONT", "Savinelli",
    "Seminole", "Sobranie", "Solani", "Stanley", "Sutliff",
    "Swan", "T&T", "TEREA", "Taste", "Three Nuns", "Vanelle",
    "Vauen", "Wessex", "Winston", "Zig Zag", "Zippo",
    # huasheng 分类名
    "彼得森", "黑马", "飞机", "马坝", "丹.", "梅维乌斯",
    "老人牌", "拉特雷", "丰收", "烟先生", "登喜路", "万宝路",
    "好味", "小皇家", "CD 康奈尔", "黑蜘蛛", "船长",
    "小骏马", "拉森", "虎牌", "红牛", "切斯特菲尔德",
    "菠萝", "罗伯特·麦康奈尔", "云斯顿", "切格瓦拉",
    "史丹利", "红场", "索拉尼", "巴厘", "蝴蝶",
    "帆船", "法官", "科尔哈斯科普", "巴西手卷", "极限",
    "罗洛", "鼓", "黑鹰桶装", "奥斯汀", "绞盘", "萨维内利",
    "水手", "斯坦威尔", "温斯洛", "霍本", "野牛",
    "华云", "天鹅", "舞女", "多明戈",
    "浅鼓", "深鼓", "古巴", "Cuban",
    "黑法官", "琥珀", "丹", "Brazil Spirit", "巴西精神",
    "索拉你", "欧亨", "McConell", "麦康奈尔", "罗伯特麦康奈尔", "黑鹰",
    "皇家酒梅", "皇家椰子菠萝", "皇家拉塔基亚", "皇家冰薄荷",
    "皇家双香草", "皇家樱桃", "皇家卡布奇诺", "皇家百香果",
    "皇家维吉尼亚", "皇家马鲁拉", "皇家浆果玫瑰", "皇家天堂茶",
    "康奈尔和迪尔", "Cornell & Diehl", "金冠", "Korona",
    "浅鼓", "深鼓", "黄巴厘", "蓝巴厘", "红巴厘",
    "原味绿GV", "ZEN", "奥斯丁", "黄绞盘方", "蓝绞盘方",
    "阿斯顿", "Ashton", "查卡姆", "Charcom", "伊尔斯特德", "Ilsted",
    "红法官", "皇家",
    # pipeuncle 品牌（补充）
    "红田", "阿姆斯特丹", "黑船长", "巴厘丝", "马霸手卷",
    "马霸选择", "马霸", "喇叭手", "美国精神", "奥尔德",
    "鼓牌", "绿GV", "手卷", "老霍本", "明亮黄",
    # nov / sp
    "Cornell & Diehl", "Peter Stokkebye", "Lane Limited",
    "Gawith Hoggarth", "Arango", "Sutliff", "F&K",
    "A&C Petersen", "Balkan Sasieni", "Borkum Riff", "Capstan",
]), key=lambda x: -len(x))

# ── 品牌和口味提取 ──

def _extract_brand_flavor(name: str):
    """从产品名称提取品牌和口味，返回 (品牌, 口味)"""
    if not name or not name.strip():
        return ("", "")
    name = name.strip()

    # 修复 HTML 实体
    name = name.replace("&#038;", "&").replace("&amp;", "&")

    matched = ""
    for brand in BRAND_DICT:
        m = re.match(re.escape(brand), name, re.IGNORECASE)
        if m:
            matched = name[:m.end()]  # 用原文中的大小写
            remaining = name[m.end():].strip()
            break
    else:
        remaining = name

    # 提取口味：去掉品牌后，去掉括号/规格/英文
    flavor = remaining
    flavor = re.sub(r'\s*\([^)]*\)\s*$', '', flavor).strip()
    flavor = re.sub(r'\s*[\d.]+[gGkK].*$', '', flavor).strip()  # 去掉 "40g" 等
    flavor = re.sub(r'\s*[a-zA-Z].*$', '', flavor).strip()
    flavor = re.sub(r'^[\s#\d\-.]+', '', flavor).strip()  # 去掉开头的 #33 等
    flavor = re.sub(r'\s+', ' ', flavor).strip()

    # 如果口味和品牌一样，则口味置空
    if flavor == matched:
        flavor = ""

    return (matched, flavor)


def _to_simplified(text: str) -> str:
    """繁转简"""
    if not text:
        return text
    return convert(text, 'zh-cn')


# ── 产品大类分类规则 ──

# huasheng 名称关键词 → 产品大类
HS_TYPE_KEYWORDS = [
    ("耗材", ["滤嘴", "空管", "卷纸", "卷烟器", "滤芯", "切角", "慢燃", "过滤嘴", "盒 ", "册 ", "册\n"]),
    ("成品烟", ["条盒", "1条", "1条10盒", "香烟"]),
    ("加热烟弹", ["terea", "加热"]),
    ("烟斗丝", ["斗丝", "彼得森", "拉森 ", "拉特雷", "萨维内利", "阿斯顿", "菠萝", "华云",
                 "斯坦威尔", "温斯洛", "科尔哈斯", "索拉尼", "罗伯特麦康奈尔"]),
    ("套餐", ["套餐", "set ", "精选"]),
]

def classify_huasheng(item):
    """Classify huasheng product by name/brand keywords."""
    text = (item.get("name", "") + " " + item.get("categories", "")).lower()
    for ptype, keywords in HS_TYPE_KEYWORDS:
        for kw in keywords:
            if kw.lower() in text:
                return ptype
    return "烟丝"


# ribenyan ftype 映射
FTYPE_MAP = {
    "1": "成品烟", "2": "成品烟",
    "3": "雪茄",
    "4": "烟丝",
    "5": "烟斗丝",
    "6": "烟丝",
    "10": "套餐",
}


# ── 各渠道转换函数 ──

def _pipeuncle(items):
    rows = []
    for item in items:
        base = {
            "渠道": "pipeuncle",
            "产品名称": item.get("name", ""),
            "品牌": item.get("brand", ""),
            "分类": item.get("category", ""),
            "成分": item.get("ingredients", ""),
            "切工": item.get("cut", ""),
            "劲道": item.get("strength", ""),
            "口味": item.get("flavor", ""),
            "是否有货": item.get("in_stock", False),
            "库存数量": item.get("total_stock", 0),
            "商品链接": "",
            "原始ID": str(item.get("id", "")),
            "产品大类": "烟丝",
        }
        price_rmb = 0
        try:
            price_rmb = float(item.get("price_rmb", 0))
        except (ValueError, TypeError):
            pass
        base["原始价格"] = price_rmb
        base["原始币种"] = "CNY"
        base["人民币价格"] = price_rmb
        base["美元价格"] = _cny_to_usd(price_rmb) if price_rmb else 0

        weight_g = 0
        # 优先从 spec 取净重 (如 "0.05kg/pack*1" → 50g)
        spec_str = item.get("spec", "")
        if spec_str:
            m = re.search(r"([\d.]+)\s*kg", spec_str, re.IGNORECASE)
            if m:
                weight_g = round(float(m.group(1)) * 1000, 1)
            else:
                m = re.search(r"([\d.]+)\s*g", spec_str, re.IGNORECASE)
                if m:
                    weight_g = round(float(m.group(1)), 1)
        # fallback: 取 weight_kg（注意这个值是毛重含包装）
        if weight_g == 0:
            w = item.get("weight_kg", "")
            if w:
                m = re.search(r"([\d.]+)\s*kg", w, re.IGNORECASE)
                if m:
                    weight_g = round(float(m.group(1)) * 1000, 1)
        base["重量(克)"] = weight_g
        base["规格"] = item.get("spec", "")

        sku_details = item.get("sku_details", [])
        if isinstance(sku_details, str):
            try:
                sku_details = json.loads(sku_details)
            except (json.JSONDecodeError, TypeError):
                sku_details = []

        if sku_details and isinstance(sku_details, list):
            for variant in sku_details:
                row = dict(base)
                row["规格"] = variant.get("spec", base["规格"])
                # pipeuncle 以 RMB 标价，variant 的 price_usd 仅作参考
                # 保持 base 的 RMB 价格不变
                # variant 重量：优先从 spec 取
                v_spec = variant.get("spec", "")
                if v_spec:
                    vm = re.search(r"([\d.]+)\s*kg", v_spec, re.IGNORECASE)
                    if vm:
                        row["重量(克)"] = round(float(vm.group(1)) * 1000, 1)
                    else:
                        vm = re.search(r"([\d.]+)\s*g", v_spec, re.IGNORECASE)
                        if vm:
                            row["重量(克)"] = round(float(vm.group(1)), 1)
                # fallback: weight_kg
                if row["重量(克)"] == 0:
                    vw = variant.get("weight_kg", "")
                    if vw:
                        vm = re.search(r"([\d.]+)\s*kg", str(vw), re.IGNORECASE)
                        if vm:
                            row["重量(克)"] = round(float(vm.group(1)) * 1000, 1)
                row["库存编码"] = variant.get("code", base.get("库存编码", ""))
                rows.append(row)
        else:
            base["库存编码"] = item.get("code", "")
            rows.append(base)
    return rows


def _huasheng(items):
    rows = []
    for item in items:
        price_fen = 0
        try:
            price_fen = float(item.get("price", 0))
        except (ValueError, TypeError):
            pass
        price_cny = price_fen / 100
        ptype = classify_huasheng(item)
        rows.append({
            "渠道": "huasheng",
            "库存编码": item.get("sku", ""),
            "产品名称": item.get("name", ""),
            "品牌": "",
            "分类": item.get("categories", ""),
            "原始价格": price_fen,
            "原始币种": "CNY",
            "美元价格": _cny_to_usd(price_cny),
            "人民币价格": price_cny,
            "重量(克)": 0,
            "规格": "",
            "是否有货": item.get("is_in_stock", False),
            "库存数量": 0,
            "商品链接": item.get("permalink", ""),
            "原始ID": str(item.get("id", "")),
            "产品大类": ptype,
        })
    return rows


def _ribenyan(items):
    rows = []
    for item in items:
        price_jpy = 0
        try:
            price_jpy = float(item.get("price", 0))
        except (ValueError, TypeError):
            pass
        ftype = str(item.get("ftype", ""))
        ptype = FTYPE_MAP.get(ftype, "其他")
        rows.append({
            "渠道": "花店",
            "库存编码": "",
            "产品名称": item.get("name", ""),
            "品牌": item.get("brand", ""),
            "分类": item.get("category", ""),
            "原始价格": price_jpy,
            "原始币种": "JPY",
            "美元价格": _jpy_to_usd(price_jpy),
            "人民币价格": _jpy_to_cny(price_jpy),
            "重量(克)": 0,
            "规格": item.get("size", ""),
            "是否有货": True,
            "库存数量": 0,
            "商品链接": item.get("url", ""),
            "原始ID": str(item.get("id", "")),
            "产品大类": ptype,
        })
    return rows


def _nov(items):
    rows = []
    for item in items:
        base = {
            "渠道": "nov",
            "产品名称": item.get("title", ""),
            "品牌": item.get("brand", ""),
            "分类": item.get("categories", "").replace("[:ATTR:]", " > "),
            "是否有货": True,
            "库存数量": int(item.get("inventory_level", 0) or 0),
            "商品链接": item.get("link", ""),
            "原始ID": str(item.get("product_id", "")),
            "产品大类": "烟斗丝",
        }
        variants = item.get("bigcommerce_variants", [])
        if variants:
            for v in variants:
                row = dict(base)
                row["库存编码"] = v.get("sku", "")
                try:
                    price = float(v.get("list_price", v.get("price", 0)))
                except (ValueError, TypeError):
                    price = 0
                row["原始价格"] = price
                row["原始币种"] = "USD"
                row["美元价格"] = price
                row["人民币价格"] = _usd_to_cny(price)

                options = v.get("options", {})
                weight_g = 0
                weight_str = options.get("Weight", "") if isinstance(options, dict) else ""
                if weight_str:
                    m = re.search(r"([\d.]+)\s*(oz|ounce|g|gram)s?", weight_str, re.IGNORECASE)
                    if m:
                        val = float(m.group(1))
                        u = m.group(2).lower()
                        weight_g = round(val * 28.3495, 1) if u in ("oz", "ounce") else val
                row["重量(克)"] = weight_g
                row["规格"] = weight_str
                row["是否有货"] = v.get("available", "1") in ("1", True)
                rows.append(row)
        else:
            base["库存编码"] = item.get("product_code", "")
            try:
                price = float(item.get("list_price", item.get("price", 0)))
            except (ValueError, TypeError):
                price = 0
            base["原始价格"] = price
            base["原始币种"] = "USD"
            base["美元价格"] = price
            base["人民币价格"] = _usd_to_cny(price)
            base["重量(克)"] = 0
            base["规格"] = ""
            rows.append(base)
    return rows


def _sp(items):
    rows = []
    for item in items:
        price = float(item.get("price_usd", 0))
        g = item.get("weight_g", 0)
        rows.append({
            "渠道": "sp",
            "库存编码": item.get("sku", ""),
            "产品名称": item.get("full_title", item.get("name", "")),
            "品牌": item.get("brand", ""),
            "分类": "",
            "原始价格": price,
            "原始币种": "USD",
            "美元价格": price,
            "人民币价格": _usd_to_cny(price),
            "重量(克)": g,
            "规格": f"{g}g",
            "是否有货": True,
            "库存数量": 0,
            "商品链接": "",
            "原始ID": item.get("sku", ""),
            "产品大类": "烟斗丝",
        })
    return rows


# ── 统一输出字段 ──
DWD_FIELDS = [
    "渠道", "库存编码", "产品名称", "品牌", "分类",
    "原始价格", "原始币种", "美元价格", "人民币价格",
    "重量(克)", "规格", "是否有货", "库存数量",
    "成分", "切工", "劲道", "口味",
    "商品链接", "原始ID",
    "产品大类",
]

SOURCES = [
    ("data/ods/pipeuncle_products.json", _pipeuncle),
    ("data/ods/huasheng_products.json", _huasheng),
    ("data/ods/ribenyan_products.json", _ribenyan),
    ("data/ods/nov_products.json", _nov),
    ("data/ods/sp_products.json", _sp),
]


def main():
    print("=" * 70)
    print("DWD LAYER BUILD")
    print("=" * 70)

    all_rows = []
    for path, fn in SOURCES:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        rows = fn(raw)
        print(f"  {path.split('/')[-1]:35s} → {len(rows)} rows")
        all_rows.extend(rows)

    print(f"\nTotal DWD rows: {len(all_rows)}")

    # ── 后处理：品牌提取 + 口味提取 + 繁转简 ──
    print("\n── 后处理 ──")
    filled_brand = 0
    filled_flavor = 0
    for r in all_rows:
        # 繁转简（中文字段）
        for txt_field in ["产品名称", "品牌", "分类", "成分", "切工", "劲道", "口味", "规格"]:
            if isinstance(r.get(txt_field), str) and r[txt_field]:
                r[txt_field] = _to_simplified(r[txt_field])

        # 品牌提取：品牌空白的从产品名提取
        if not r["品牌"]:
            extracted_brand, extracted_flavor = _extract_brand_flavor(r["产品名称"])
            if extracted_brand:
                r["品牌"] = _to_simplified(extracted_brand)
                filled_brand += 1
            # 同时提取口味
            if extracted_flavor and not r.get("口味"):
                r["口味"] = _to_simplified(extracted_flavor)
                filled_flavor += 1

    print(f"  品牌提取填充: {filled_brand} 条")
    print(f"  口味提取填充: {filled_flavor} 条")

    # ── 从产品名称提取重量 ──
    OZ_TO_G = 28.3495
    weight_patterns = [
        (r'(\d+\.?\d*)\s*[gG](?=[^a-zA-Z0-9]|$)', 'g'),
        (r'(\d+\.?\d*)克', 'g'),
        (r'(\d+\.?\d*)\s*[oO][zZ](?=[^a-zA-Z0-9]|$)', 'oz'),
    ]
    filled_weight = 0
    for r in all_rows:
        if r.get("重量(克)"):
            continue
        name = r.get("产品名称", "")
        for pat, unit in weight_patterns:
            m = re.search(pat, name)
            if m:
                val = float(m.group(1))
                w = round(val * OZ_TO_G, 1) if unit == 'oz' else val
                r["重量(克)"] = w
                filled_weight += 1
                break
    print(f"  从名称提取重量: {filled_weight} 条")

    os.makedirs("data/dwd", exist_ok=True)

    csv_path = "data/dwd/product_detail.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DWD_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"CSV: {csv_path}")

    json_path = "data/dwd/product_detail.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print(f"JSON: {json_path}")

    # 渠道统计
    ch = {}
    for r in all_rows:
        c = r["渠道"]
        ch[c] = ch.get(c, 0) + 1
    print(f"\n各渠道行数:")
    for k, v in sorted(ch.items()):
        print(f"  {k}: {v}")

    # 产品大类统计
    pt = {}
    for r in all_rows:
        p = r.get("产品大类", "未知")
        pt[p] = pt.get(p, 0) + 1
    print(f"\n产品大类分布:")
    for k, v in sorted(pt.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
