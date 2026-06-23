"""
Build DWD (Data Warehouse Detail) layer from ODS raw data.
Unifies all channel schemas into a common product_detail table with:
- Chinese field names
- Unified currency conversion (USD + CNY)
- Weight normalization (oz/kg → g)
- Variant expansion (one row per SKU)
- Product type classification (手卷丝/烟斗丝/成品烟/耗材/...)
"""
import json
import csv
import os
import re

# ── 汇率 ──
USD_CNY = 6.79
USD_JPY = 145.0
JPY_CNY = 0.0468

def _cny_to_usd(cny): return round(cny / USD_CNY, 4)
def _usd_to_cny(usd): return round(usd * USD_CNY, 4)
def _jpy_to_cny(jpy): return round(jpy * JPY_CNY, 4)
def _jpy_to_usd(jpy): return round(jpy / USD_JPY, 4)

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
    return "手卷丝"


# ribenyan ftype 映射
FTYPE_MAP = {
    "1": "成品烟", "2": "成品烟",
    "3": "雪茄",
    "4": "手卷丝",
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
            "产品大类": "手卷丝",
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
                try:
                    v_price = float(variant.get("price_usd", 0))
                    row["原始价格"] = v_price
                    row["原始币种"] = "USD"
                    row["美元价格"] = v_price
                    row["人民币价格"] = _usd_to_cny(v_price)
                except (ValueError, TypeError):
                    pass
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
            "渠道": "ribenyan",
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
