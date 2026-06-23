"""
Build DWS (summary) and ADS (application) layers from DWD.
All field names in Chinese, includes product type classification.
"""
import json
import csv
import os
from collections import defaultdict

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
# DWS
# ════════════════════════════════════════════════════════════

def build_dws_channel_overview(dwd):
    """各渠道概览"""
    ch = defaultdict(lambda: {"pids": set(), "brands": set(), "prices": [], "weights": [], "types": set()})
    for r in dwd:
        c = r["渠道"]
        ch[c]["pids"].add(r["原始ID"])
        ch[c]["brands"].add(r["品牌"])
        ch[c]["types"].add(r.get("产品大类", ""))
        try: ch[c]["prices"].append(float(r["人民币价格"]))
        except: pass
        try:
            w = float(r["重量(克)"])
            if w > 0: ch[c]["weights"].append(w)
        except: pass

    rows = []
    fields = ["渠道", "产品数", "品牌数", "产品大类", "最低价(¥)", "最高价(¥)", "均价(¥)", "最小重量(g)", "最大重量(g)"]
    for c, d in sorted(ch.items()):
        p = d["prices"]; w = d["weights"]
        rows.append({
            "渠道": c, "产品数": len(d["pids"]), "品牌数": len(d["brands"]),
            "产品大类": " | ".join(sorted(d["types"])),
            "最低价(¥)": round(min(p),2) if p else "",
            "最高价(¥)": round(max(p),2) if p else "",
            "均价(¥)": round(sum(p)/len(p),2) if p else "",
            "最小重量(g)": round(min(w),1) if w else "",
            "最大重量(g)": round(max(w),1) if w else "",
        })
    save_csv(rows, "data/dws/channel_overview.csv", fields)

def build_dws_price_by_brand(dwd):
    """按品牌价格对比"""
    bd = defaultdict(lambda: {"chs": set(), "pcny": [], "pusd": [], "ws": [], "types": set()})
    for r in dwd:
        b = r["品牌"] or "未知"
        bd[b]["chs"].add(r["渠道"])
        bd[b]["types"].add(r.get("产品大类", ""))
        try: bd[b]["pcny"].append(float(r["人民币价格"]))
        except: pass
        try: bd[b]["pusd"].append(float(r["美元价格"]))
        except: pass
        try:
            w = float(r["重量(克)"])
            if w > 0: bd[b]["ws"].append(w)
        except: pass

    rows = []
    fields = ["品牌", "覆盖渠道", "产品大类", "产品数", "最低价(¥)", "最高价(¥)", "均价(¥)", "均价($)", "最小重量(g)", "最大重量(g)"]
    for b, d in sorted(bd.items()):
        pc = d["pcny"]; pu = d["pusd"]; ws = d["ws"]
        rows.append({
            "品牌": b, "覆盖渠道": " | ".join(sorted(d["chs"])),
            "产品大类": " | ".join(sorted(d["types"])),
            "产品数": len(pc),
            "最低价(¥)": round(min(pc),2) if pc else "",
            "最高价(¥)": round(max(pc),2) if pc else "",
            "均价(¥)": round(sum(pc)/len(pc),2) if pc else "",
            "均价($)": round(sum(pu)/len(pu),2) if pu else "",
            "最小重量(g)": round(min(ws),1) if ws else "",
            "最大重量(g)": round(max(ws),1) if ws else "",
        })
    save_csv(rows, "data/dws/price_by_brand.csv", fields)


def build_dws_price_calculations(dwd):
    """价格计算表：含税价、克单价、500g单价、20支成本"""
    rows = []
    fields = ["渠道", "产品名称", "品牌", "产品大类", "重量(克)",
              "商品价¥", "含税价¥", "克单价¥/g", "500g单价¥", "20支成本¥"]
    for r in dwd:
        price_cny = r["人民币价格"]
        weight = r["重量(克)"]
        tax_price = round(price_cny * 1.5, 2)
        per_g = ""
        per_500g = ""
        cost_20 = ""
        if isinstance(weight, (int, float)) and weight > 0:
            per_g = round(tax_price / weight, 2)
            per_500g = round(per_g * 500, 2)
            cost_20 = round(12 * per_g + 3.50, 2)
        rows.append({
            "渠道": r["渠道"], "产品名称": r["产品名称"], "品牌": r["品牌"],
            "产品大类": r.get("产品大类", ""), "重量(克)": weight,
            "商品价¥": price_cny, "含税价¥": tax_price,
            "克单价¥/g": per_g, "500g单价¥": per_500g, "20支成本¥": cost_20,
        })
    save_csv(rows, "data/dws/price_calculations.csv", fields)
    # 只取有重量数据的行单独保存
    has_weight = [r for r in rows if r["克单价¥/g"] != ""]
    save_csv(has_weight, "data/dws/price_per_gram.csv",
             ["渠道", "产品名称", "品牌", "产品大类", "重量(克)",
              "含税价¥", "克单价¥/g", "500g单价¥", "20支成本¥"])

def build_dws_price_by_type(dwd):
    """按产品大类汇总"""
    td = defaultdict(lambda: {"chs": set(), "brands": set(), "pcny": [], "ws": []})
    for r in dwd:
        t = r.get("产品大类", "其他")
        td[t]["chs"].add(r["渠道"])
        td[t]["brands"].add(r["品牌"])
        try: td[t]["pcny"].append(float(r["人民币价格"]))
        except: pass
        try:
            w = float(r["重量(克)"])
            if w > 0: td[t]["ws"].append(w)
        except: pass

    rows = []
    fields = ["产品大类", "覆盖渠道", "品牌数", "产品数", "最低价(¥)", "最高价(¥)", "均价(¥)", "最小重量(g)", "最大重量(g)"]
    for t, d in sorted(td.items(), key=lambda x: -len(x[1]["pcny"])):
        pc = d["pcny"]; ws = d["ws"]
        rows.append({
            "产品大类": t, "覆盖渠道": " | ".join(sorted(d["chs"])),
            "品牌数": len(d["brands"]), "产品数": len(pc),
            "最低价(¥)": round(min(pc),2) if pc else "",
            "最高价(¥)": round(max(pc),2) if pc else "",
            "均价(¥)": round(sum(pc)/len(pc),2) if pc else "",
            "最小重量(g)": round(min(ws),1) if ws else "",
            "最大重量(g)": round(max(ws),1) if ws else "",
        })
    save_csv(rows, "data/dws/price_by_type.csv", fields)

def build_dws_price_by_weight_range(dwd):
    """按重量段分布"""
    ranges = [
        ("≤50g", 0, 50), ("51-100g", 50, 100), ("101-200g", 100, 200),
        ("201-500g", 200, 500), (">500g", 500, float("inf")), ("未知重量", -1, 0),
    ]
    rd = {l: {"chs": set(), "pcny": [], "types": set()} for l,_,_ in ranges}
    for r in dwd:
        try: w = float(r["重量(克)"])
        except: w = -1
        for l, lo, hi in ranges:
            if lo < w <= hi:
                rd[l]["chs"].add(r["渠道"])
                rd[l]["types"].add(r.get("产品大类", ""))
                try: rd[l]["pcny"].append(float(r["人民币价格"]))
                except: pass
                break

    rows = []
    fields = ["重量段", "产品数", "覆盖渠道", "产品大类", "最低价(¥)", "最高价(¥)", "均价(¥)"]
    for l, _, _ in ranges:
        d = rd[l]; p = d["pcny"]
        if not p: continue
        rows.append({
            "重量段": l, "产品数": len(p),
            "覆盖渠道": " | ".join(sorted(d["chs"])),
            "产品大类": " | ".join(sorted(d["types"])),
            "最低价(¥)": round(min(p),2), "最高价(¥)": round(max(p),2), "均价(¥)": round(sum(p)/len(p),2),
        })
    save_csv(rows, "data/dws/price_by_weight_range.csv", fields)


# ════════════════════════════════════════════════════════════
# ADS
# ════════════════════════════════════════════════════════════

def build_ads_products(dwd):
    """应用层产品数据"""
    ads = []
    for r in dwd:
        ads.append({
            "渠道": r["渠道"], "产品名称": r["产品名称"], "品牌": r["品牌"],
            "口味": r.get("口味", ""), "产品大类": r.get("产品大类", ""), "分类": r["分类"],
            "美元价格": r["美元价格"], "人民币价格": r["人民币价格"],
            "重量(克)": r["重量(克)"], "规格": r["规格"],
            "是否有货": "有货" if r["是否有货"] else "无货",
            "商品链接": r["商品链接"],
        })
    save_json(ads, "data/ads/products.json")

def build_ads_type_summary(dwd):
    """按产品大类的应用层汇总"""
    td = defaultdict(list)
    for r in dwd:
        td[r.get("产品大类", "其他")].append({
            "渠道": r["渠道"], "产品名称": r["产品名称"], "品牌": r["品牌"],
            "原始价格": r["原始价格"], "原始币种": r["原始币种"],
            "美元价格": r["美元价格"], "人民币价格": r["人民币价格"],
            "重量(克)": r["重量(克)"], "规格": r["规格"],
            "是否有货": "有货" if r["是否有货"] else "无货",
        })
    save_json(dict(td), "data/ads/products_by_type.json")

# ════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("DWS & ADS LAYER BUILD")
    print("=" * 70)

    dwd = load_dwd()
    print(f"\nLoaded DWD: {len(dwd)} rows\n")

    print("── DWS ──")
    build_dws_channel_overview(dwd)
    build_dws_price_by_brand(dwd)
    build_dws_price_by_type(dwd)
    build_dws_price_by_weight_range(dwd)
    build_dws_price_calculations(dwd)

    print("\n── ADS ──")
    build_ads_products(dwd)
    build_ads_type_summary(dwd)

    print("\nDone.")

if __name__ == "__main__":
    main()
