"""
Build DWS (summary) and ADS (application) layers from DWD.
"""
import json
import csv
import os
from collections import defaultdict

# ── 工具函数 ──

def load_dwd():
    with open("data/dwd/product_detail.json", encoding="utf-8") as f:
        return json.load(f)


def save_csv(rows, path, fieldnames):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  CSV: {path} ({len(rows)} rows)")


def save_json(data, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {path}")


# ════════════════════════════════════════════════════════════
# DWS 汇总层
# ════════════════════════════════════════════════════════════

def build_dws_channel_overview(dwd):
    """各渠道概览：产品数、价格区间、重量区间"""
    ch_data = defaultdict(lambda: {"products": set(), "prices": [], "weights": [], "brands": set()})
    for row in dwd:
        c = row["channel"]
        ch_data[c]["products"].add(row.get("original_id", ""))
        ch_data[c]["brands"].add(row["brand"])
        try:
            ch_data[c]["prices"].append(float(row["price_cny"]))
        except (ValueError, TypeError):
            pass
        try:
            w = float(row["weight_g"])
            if w > 0:
                ch_data[c]["weights"].append(w)
        except (ValueError, TypeError):
            pass

    rows = []
    fields = ["渠道", "产品数", "品牌数", "最低价(CNY)", "最高价(CNY)", "均价(CNY)", "最小重量(g)", "最大重量(g)"]
    for ch, data in sorted(ch_data.items()):
        prices = data["prices"]
        weights = data["weights"]
        rows.append({
            "渠道": ch,
            "产品数": len(data["products"]),
            "品牌数": len(data["brands"]),
            "最低价(CNY)": round(min(prices), 2) if prices else "",
            "最高价(CNY)": round(max(prices), 2) if prices else "",
            "均价(CNY)": round(sum(prices) / len(prices), 2) if prices else "",
            "最小重量(g)": round(min(weights), 1) if weights else "",
            "最大重量(g)": round(max(weights), 1) if weights else "",
        })
    save_csv(rows, "data/dws/channel_overview.csv", fields)
    return rows


def build_dws_price_by_brand(dwd):
    """按品牌的价格对比"""
    brand_data = defaultdict(lambda: {"channels": set(), "prices_cny": [], "prices_usd": [], "weights": []})
    for row in dwd:
        b = row["brand"] or "未知"
        brand_data[b]["channels"].add(row["channel"])
        try:
            brand_data[b]["prices_cny"].append(float(row["price_cny"]))
            brand_data[b]["prices_usd"].append(float(row["price_usd"]))
        except (ValueError, TypeError):
            pass
        try:
            w = float(row["weight_g"])
            if w > 0:
                brand_data[b]["weights"].append(w)
        except (ValueError, TypeError):
            pass

    rows = []
    fields = ["品牌", "覆盖渠道", "渠道数", "产品数", "最低价(CNY)", "最高价(CNY)", "均价(CNY)", "均价(USD)", "最小重量(g)", "最大重量(g)"]
    for brand, data in sorted(brand_data.items()):
        p = data["prices_cny"]
        pu = data["prices_usd"]
        w = data["weights"]
        rows.append({
            "品牌": brand,
            "覆盖渠道": " | ".join(sorted(data["channels"])),
            "渠道数": len(data["channels"]),
            "产品数": len(p),
            "最低价(CNY)": round(min(p), 2) if p else "",
            "最高价(CNY)": round(max(p), 2) if p else "",
            "均价(CNY)": round(sum(p) / len(p), 2) if p else "",
            "均价(USD)": round(sum(pu) / len(pu), 2) if pu else "",
            "最小重量(g)": round(min(w), 1) if w else "",
            "最大重量(g)": round(max(w), 1) if w else "",
        })
    save_csv(rows, "data/dws/price_by_brand.csv", fields)
    return rows


def build_dws_price_by_weight_range(dwd):
    """按重量段的价格对比"""
    ranges = [
        ("≤50g", 0, 50),
        ("51-100g", 50, 100),
        ("101-200g", 100, 200),
        ("201-500g", 200, 500),
        (">500g", 500, float("inf")),
        ("未知重量", -1, 0),
    ]

    range_data = {label: {"channels": set(), "prices_cny": []} for label, _, _ in ranges}

    for row in dwd:
        try:
            w = float(row["weight_g"])
        except (ValueError, TypeError):
            w = -1
        for label, lo, hi in ranges:
            if lo < w <= hi:
                range_data[label]["channels"].add(row["channel"])
                try:
                    range_data[label]["prices_cny"].append(float(row["price_cny"]))
                except (ValueError, TypeError):
                    pass
                break

    rows = []
    fields = ["重量段", "产品数", "覆盖渠道", "最低价(CNY)", "最高价(CNY)", "均价(CNY)"]
    for label, _, _ in ranges:
        d = range_data[label]
        p = d["prices_cny"]
        if not p:
            continue
        rows.append({
            "重量段": label,
            "产品数": len(p),
            "覆盖渠道": " | ".join(sorted(d["channels"])),
            "最低价(CNY)": round(min(p), 2),
            "最高价(CNY)": round(max(p), 2),
            "均价(CNY)": round(sum(p) / len(p), 2),
        })
    save_csv(rows, "data/dws/price_by_weight_range.csv", fields)
    return rows


# ════════════════════════════════════════════════════════════
# ADS 应用层
# ════════════════════════════════════════════════════════════

def build_ads_product_summary(dwd):
    """前端用产品汇总 JSON"""
    summary = []
    for row in dwd:
        summary.append({
            "渠道": row["channel"],
            "产品名称": row["product_name"],
            "品牌": row["brand"],
            "分类": row["category"],
            "美元价格": row["price_usd"],
            "人民币价格": row["price_cny"],
            "重量(g)": row["weight_g"],
            "规格": row["spec"],
            "库存": "有货" if row["in_stock"] else "无货",
            "链接": row["url"],
        })
    save_json(summary, "data/ads/products.json")
    return summary


# ════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("DWS & ADS LAYER BUILD")
    print("=" * 70)

    dwd = load_dwd()
    print(f"\nLoaded DWD: {len(dwd)} rows\n")

    print("── DWS 汇总层 ──")
    build_dws_channel_overview(dwd)
    build_dws_price_by_brand(dwd)
    build_dws_price_by_weight_range(dwd)

    print("\n── ADS 应用层 ──")
    build_ads_product_summary(dwd)

    print("\nDone.")


if __name__ == "__main__":
    main()
