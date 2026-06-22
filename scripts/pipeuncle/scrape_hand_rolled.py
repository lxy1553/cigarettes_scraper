"""
Scrape all hand-rolled tobacco (手卷丝) products from pipeuncle.com and generate a CSV table.
"""
import csv
import json
import os
import re
import sys
import time
import requests

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, "../utils"))
from decrypt import api_get

BASE_URL = "https://www.pipeuncle.com"
OUTPUT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "../../data/pipeuncle"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def get_product_detail(product_id: int) -> dict:
    """Get detailed product information."""
    try:
        result = api_get(f"{BASE_URL}/api/goods/detail", {"id": product_id})
        return result.get("data", {})
    except Exception as e:
        print(f"    Error: {e}")
        return {}


def extract_specs(detail: dict) -> dict:
    """Extract structured specs from product detail."""
    specs = {}

    # Extract spec values (weight per pack, etc.)
    spec_values = detail.get("specValue", [])
    if spec_values:
        for sv in spec_values:
            spec_name = sv.get("name", "")
            spec_list = sv.get("specList", [])
            if spec_list:
                specs[spec_name] = ", ".join(s.get("value", "") for s in spec_list)

    # Extract additional attributes
    attrs = detail.get("additionalAttributes", [])
    for attr in attrs:
        name_info = attr.get("name", {})
        value_info = attr.get("value", {})
        unit_info = attr.get("unit", {})
        # Prefer zh_cn name
        attr_name = name_info.get("zh_cn", name_info.get("en", ""))
        attr_value = value_info.get("zh_cn", value_info.get("en", ""))
        attr_unit = unit_info.get("zh_cn", unit_info.get("en", ""))
        if attr_name and attr_value:
            specs[attr_name] = f"{attr_value} {attr_unit}".strip()

    # Extract info from HTML content
    content = detail.get("content", "")
    if content:
        # Category/type
        m = re.search(r'<strong>類別[：:]\s*</strong>\s*(.+?)(?:<br|</p)', content)
        if m:
            specs["类别"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # Ingredients
        m = re.search(r'<strong>成分[：:]\s*</strong>\s*(.+?)(?:<br|</p)', content)
        if m:
            specs["成分"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # Cut/format
        m = re.search(r'<strong>形製[：:]?\s*</strong>\s*(.+?)(?:<br|</p)', content)
        if m:
            specs["形制"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # Strength
        m = re.search(r'<strong>勁道[：:]\s*</strong>\s*(.+?)(?:<br|</p)', content)
        if m:
            specs["劲道"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # Blend
        m = re.search(r'<strong>調配[：:]\s*</strong>\s*(.+?)(?:<br|</p)', content)
        if m:
            specs["调配"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # Flavor
        m = re.search(r'<strong>風味[：:]\s*</strong>\s*(.+?)(?:<br|</p)', content)
        if m:
            specs["风味"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()

    return specs


def scrape_all_hand_rolled() -> list:
    """Scrape all hand-rolled tobacco products."""

    # Step 1: Get base product list from category 70 (手卷丝)
    print("Fetching product list from category 70 (手卷丝)...")
    result = api_get(f"{BASE_URL}/api/goods/limit", {
        "categoryId": 70,
        "limit": 100,
        "type": 1
    })
    products = result.get("data", [])
    print(f"  Got {len(products)} products from main category")

    # Track seen IDs
    seen_ids = {p["id"] for p in products}

    # Step 2: Also try subcategories for any additional products
    subcategories = {
        72: "喇叭手", 80: "金弗吉尼亚", 182: "老霍本", 71: "鼓牌",
        193: "美国精神", 119: "黑船长", 197: "红田RF", 162: "小马牌克鲁斯",
        183: "马霸", 179: "巴厘丝", 192: "彼得斯托克拜", 185: "CHOICE选择",
        184: "阿姆斯特丹", 196: "史丹利", 181: "加维霍格斯"
    }

    for cid, cname in subcategories.items():
        result = api_get(f"{BASE_URL}/api/goods/limit", {
            "categoryId": cid,
            "limit": 100,
            "type": 1
        })
        sub_products = result.get("data", [])
        new_count = 0
        for p in sub_products:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                products.append(p)
                new_count += 1
        if new_count > 0:
            print(f"  +{new_count} new from {cname} (ID={cid})")

    # Step 3: Also check combo category (手卷丝组合)
    result = api_get(f"{BASE_URL}/api/goods/limit", {
        "categoryId": 146,
        "limit": 100,
        "type": 1
    })
    combo_products = result.get("data", [])
    for p in combo_products:
        if p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            products.append(p)
            print(f"  +1 new from 手卷丝组合")

    print(f"\nTotal unique products to scrape: {len(products)}")

    # Step 4: Get detailed info for each product
    detailed_products = []
    for i, product in enumerate(products):
        pid = product["id"]
        name = product["name"].replace("\n", " ").strip()
        print(f"[{i+1}/{len(products)}] {name} (ID={pid})")

        detail = get_product_detail(pid)
        specs = extract_specs(detail) if detail else {}
        time.sleep(0.3)  # Rate limiting

        # Determine category name from category IDs
        cat_ids = detail.get("categoryId", [])
        cat_name = "手卷丝"
        if 146 in cat_ids:
            cat_name = "手卷丝组合"

        # Get spec values for weight
        spec_values = detail.get("specValueList", [])
        spec_str = ""
        if spec_values:
            for sv in spec_values:
                if sv.get("skuValueArr"):
                    spec_str = sv["skuValueArr"]
                    break

        # Get SKU details
        sku_details = []
        for sv in detail.get("specValueList", []):
            sku_details.append({
                "spec": sv.get("skuValueArr", ""),
                "price_usd": sv.get("price", ""),
                "stock": sv.get("stock", ""),
            })

        merged = {
            # Basic info
            "id": pid,
            "code": detail.get("code", ""),
            "name": name,
            "category": cat_name,
            "brand": "",

            # Pricing
            "price_usd": product.get("price", ""),
            "price_rmb": product.get("aboutRmb", ""),
            "lineation_price": product.get("lineationPrice", ""),

            # Specs
            "spec": spec_str,
            "weight_kg": specs.get("毛重", ""),
            "category_type": specs.get("类别", ""),
            "ingredients": specs.get("成分", ""),
            "cut": specs.get("形制", ""),
            "strength": specs.get("劲道", ""),
            "blend": specs.get("调配", ""),
            "flavor": specs.get("风味", ""),

            # Stock & sales
            "total_stock": detail.get("totalStock", ""),
            "sales_num": product.get("salesNum", ""),
            "in_stock": product.get("inventoryStatus", ""),
            "stock_warning": detail.get("stockWarning", ""),

            # Other
            "subtitle": product.get("subtitle", ""),
            "is_multiple": product.get("isMultiple", ""),
            "image": product.get("image", ""),
            "description": detail.get("description", ""),
            "content_html": detail.get("content", ""),
            "sku_details": json.dumps(sku_details, ensure_ascii=False),
        }

        detailed_products.append(merged)

    return detailed_products


def main():
    print("=" * 70)
    print("PIPEUNCLE.COM - Hand-Rolled Tobacco (手卷丝) Scraper")
    print("=" * 70)

    products = scrape_all_hand_rolled()

    print(f"\n{'=' * 70}")
    print(f"Scraping complete! Total products: {len(products)}")
    print(f"{'=' * 70}")

    # Save as CSV
    csv_path = os.path.join(OUTPUT_DIR, "hand_rolled.csv")
    fieldnames = [
        "id", "code", "name", "category", "brand",
        "spec", "weight_kg",
        "category_type", "ingredients", "cut", "strength", "blend", "flavor",
        "price_usd", "price_rmb", "lineation_price",
        "total_stock", "sales_num", "in_stock", "stock_warning",
        "subtitle", "is_multiple", "description",
        "image", "sku_details"
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)
    print(f"\nCSV saved to: {csv_path}")

    # Save as JSON
    json_path = os.path.join(OUTPUT_DIR, "hand_rolled.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"JSON saved to: {json_path}")

    # Print summary
    in_stock = [p for p in products if p["in_stock"] == True]
    out_of_stock = [p for p in products if p["in_stock"] == False]
    print(f"\nSummary:")
    print(f"  In stock: {len(in_stock)}")
    print(f"  Out of stock: {len(out_of_stock)}")
    print(f"  Total: {len(products)}")

    # Price range
    prices = [float(p["price_usd"]) for p in products if p["price_usd"]]
    if prices:
        print(f"  Price range: \${min(prices):.2f} - \${max(prices):.2f} USD")

    # By brand/spec
    specs = {}
    for p in products:
        s = p.get("category_type", "未知")
        specs[s] = specs.get(s, 0) + 1
    if specs:
        print(f"\n  类别分布:")
        for k, v in sorted(specs.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
