"""
Build DWD (Data Warehouse Detail) layer from ODS raw data.
Unifies all channel schemas into a common product_detail table with:
- Unified currency conversion (USD + CNY)
- Weight normalization (oz/kg → g)
- Variant expansion (one row per SKU)
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

# ── 各渠道转换函数 ──

def _pipeuncle(items):
    rows = []
    for item in items:
        base = {
            "channel": "pipeuncle",
            "product_name": item.get("name", ""),
            "brand": item.get("brand", ""),
            "category": item.get("category", ""),
            "ingredients": item.get("ingredients", ""),
            "cut": item.get("cut", ""),
            "strength": item.get("strength", ""),
            "flavor": item.get("flavor", ""),
            "in_stock": item.get("in_stock", False),
            "stock_qty": item.get("total_stock", 0),
            "url": "",
            "original_id": str(item.get("id", "")),
            "code": item.get("code", ""),
        }
        price_rmb = 0
        try:
            price_rmb = float(item.get("price_rmb", 0))
        except (ValueError, TypeError):
            pass
        base["price_original"] = price_rmb
        base["currency"] = "CNY"
        base["price_cny"] = price_rmb
        base["price_usd"] = _cny_to_usd(price_rmb) if price_rmb else 0

        weight_g = 0
        w = item.get("weight_kg", "")
        if w:
            m = re.search(r"([\d.]+)\s*kg", w, re.IGNORECASE)
            if m:
                weight_g = round(float(m.group(1)) * 1000, 1)
        base["weight_g"] = weight_g
        base["spec"] = item.get("spec", "")

        sku_details = item.get("sku_details", [])
        if isinstance(sku_details, str):
            try:
                sku_details = json.loads(sku_details)
            except (json.JSONDecodeError, TypeError):
                sku_details = []

        if sku_details and isinstance(sku_details, list):
            for variant in sku_details:
                row = dict(base)
                row["spec"] = variant.get("spec", base["spec"])
                try:
                    v_price = float(variant.get("price_usd", 0))
                    row["price_original"] = v_price
                    row["currency"] = "USD"
                    row["price_usd"] = v_price
                    row["price_cny"] = _usd_to_cny(v_price)
                except (ValueError, TypeError):
                    pass
                vw = variant.get("weight_kg", "")
                if vw:
                    vm = re.search(r"([\d.]+)\s*kg", str(vw), re.IGNORECASE)
                    if vm:
                        row["weight_g"] = round(float(vm.group(1)) * 1000, 1)
                row["sku"] = variant.get("code", base["code"])
                rows.append(row)
        else:
            base["sku"] = item.get("code", "")
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
        rows.append({
            "channel": "huasheng",
            "sku": item.get("sku", ""),
            "product_name": item.get("name", ""),
            "brand": "",
            "category": item.get("categories", ""),
            "price_original": price_fen,
            "currency": "CNY",
            "price_usd": _cny_to_usd(price_cny),
            "price_cny": price_cny,
            "weight_g": 0,
            "spec": "",
            "in_stock": item.get("is_in_stock", False),
            "stock_qty": 0,
            "url": item.get("permalink", ""),
            "original_id": str(item.get("id", "")),
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
        rows.append({
            "channel": "ribenyan",
            "sku": "",
            "product_name": item.get("name", ""),
            "brand": item.get("brand", ""),
            "category": item.get("category", ""),
            "price_original": price_jpy,
            "currency": "JPY",
            "price_usd": _jpy_to_usd(price_jpy),
            "price_cny": _jpy_to_cny(price_jpy),
            "weight_g": 0,
            "spec": item.get("size", ""),
            "in_stock": True,
            "stock_qty": 0,
            "url": item.get("url", ""),
            "original_id": str(item.get("id", "")),
        })
    return rows


def _nov(items):
    rows = []
    for item in items:
        base = {
            "channel": "nov",
            "product_name": item.get("title", ""),
            "brand": item.get("brand", ""),
            "category": item.get("categories", "").replace("[:ATTR:]", " > "),
            "in_stock": True,
            "stock_qty": int(item.get("inventory_level", 0) or 0),
            "url": item.get("link", ""),
            "original_id": str(item.get("product_id", "")),
        }
        variants = item.get("bigcommerce_variants", [])
        if variants:
            for v in variants:
                row = dict(base)
                row["sku"] = v.get("sku", "")
                try:
                    price = float(v.get("list_price", v.get("price", 0)))
                except (ValueError, TypeError):
                    price = 0
                row["price_original"] = price
                row["currency"] = "USD"
                row["price_usd"] = price
                row["price_cny"] = _usd_to_cny(price)

                options = v.get("options", {})
                weight_g = 0
                weight_str = options.get("Weight", "") if isinstance(options, dict) else ""
                if weight_str:
                    m = re.search(r"([\d.]+)\s*(oz|ounce|g|gram)s?", weight_str, re.IGNORECASE)
                    if m:
                        val = float(m.group(1))
                        u = m.group(2).lower()
                        weight_g = round(val * 28.3495, 1) if u in ("oz", "ounce") else val
                row["weight_g"] = weight_g
                row["spec"] = weight_str
                row["in_stock"] = v.get("available", "1") in ("1", True)
                rows.append(row)
        else:
            base["sku"] = item.get("product_code", "")
            try:
                price = float(item.get("list_price", item.get("price", 0)))
            except (ValueError, TypeError):
                price = 0
            base["price_original"] = price
            base["currency"] = "USD"
            base["price_usd"] = price
            base["price_cny"] = _usd_to_cny(price)
            base["weight_g"] = 0
            base["spec"] = ""
            rows.append(base)
    return rows


def _sp(items):
    rows = []
    for item in items:
        price = float(item.get("price_usd", 0))
        g = item.get("weight_g", 0)
        rows.append({
            "channel": "sp",
            "sku": item.get("sku", ""),
            "product_name": item.get("full_title", item.get("name", "")),
            "brand": item.get("brand", ""),
            "category": "",
            "price_original": price,
            "currency": "USD",
            "price_usd": price,
            "price_cny": _usd_to_cny(price),
            "weight_g": g,
            "spec": f"{g}g",
            "in_stock": True,
            "stock_qty": 0,
            "url": "",
            "original_id": item.get("sku", ""),
        })
    return rows


# ── 统一输出字段 ──
DWD_FIELDS = [
    "channel", "sku", "product_name", "brand", "category",
    "price_original", "currency", "price_usd", "price_cny",
    "weight_g", "spec", "in_stock", "stock_qty", "url", "original_id",
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
        c = r["channel"]
        ch[c] = ch.get(c, 0) + 1
    print(f"\n各渠道行数:")
    for k, v in sorted(ch.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
