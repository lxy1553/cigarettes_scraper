"""
Scrape ALL products from pipeuncle.com EXCEPT 手卷丝 (hand-rolled tobacco).
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

# Categories to scrape (all except 手卷丝 and 手卷丝組合)
CATEGORIES = {
    # Top-level categories that include all their subcategories
    44: "雪茄",
    151: "古巴雪茄",
    30: "煙斗絲",
    144: "雪茄組合",
    79: "煙斗絲組合",
    109: "新手精選",
    139: "拍賣專場",
}

# 手卷丝 related category IDs to exclude
HAND_ROLLED_IDS = {70, 71, 72, 80, 119, 146, 162, 179, 181, 182, 183, 184, 185, 192, 193, 196, 197}

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

    # Extract spec values
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


def scrape_all_products() -> list:
    """Scrape all products except hand-rolled tobacco."""

    seen_ids = set()
    all_products = []

    # Step 1: Get products from each target category
    for cat_id, cat_name in CATEGORIES.items():
        print(f"\nFetching products from {cat_name} (ID={cat_id})...")
        result = api_get(f"{BASE_URL}/api/goods/limit", {
            "categoryId": cat_id,
            "limit": 2000,
            "type": 1
        })
        products = result.get("data", [])
        new_count = 0
        for p in products:
            pid = p["id"]
            if pid not in seen_ids:
                # Double-check: skip if this product belongs to 手卷丝 categories
                # We'll do a deeper check after getting detail
                seen_ids.add(pid)
                all_products.append(p)
                new_count += 1
        print(f"  Got {len(products)} products, {new_count} new (total unique: {len(all_products)})")

    print(f"\n{'=' * 70}")
    print(f"Total unique products to scrape: {len(all_products)}")
    print(f"{'=' * 70}")

    # Step 2: Get detailed info for each product
    detailed_products = []
    skipped_hand_rolled = 0

    for i, product in enumerate(all_products):
        pid = product["id"]
        name = product["name"].replace("\n", " ").strip()
        print(f"[{i+1}/{len(all_products)}] {name} (ID={pid})")

        detail = get_product_detail(pid)
        # Handle case where API returns a list instead of dict
        if isinstance(detail, list):
            detail = {}

        # Skip if product belongs to 手卷丝 categories
        cat_ids = detail.get("categoryId", []) if detail else []
        if cat_ids and any(cid in HAND_ROLLED_IDS for cid in cat_ids):
            print(f"    SKIPPING: belongs to 手卷丝 (cat IDs: {cat_ids})")
            skipped_hand_rolled += 1
            continue

        specs = extract_specs(detail) if detail else {}

        # Determine category name from category IDs
        cat_name = "其他"
        for cid in cat_ids:
            if cid in CATEGORIES:
                cat_name = CATEGORIES[cid]
                break

        # Get spec values
        spec_values = detail.get("specValueList", []) if detail else []
        spec_str = ""
        if spec_values:
            for sv in spec_values:
                if isinstance(sv, dict) and sv.get("skuValueArr"):
                    spec_str = sv["skuValueArr"]
                    break

        # Get SKU details
        sku_details = []
        for sv in (detail.get("specValueList", []) if detail else []):
            if isinstance(sv, dict):
                sku_details.append({
                    "spec": sv.get("skuValueArr", ""),
                    "price_usd": sv.get("price", ""),
                    "stock": sv.get("stock", ""),
                })

        price_usd = product.get("price", "")
        # Try to get price from SKU if not in product
        if not price_usd and detail and detail.get("specValueList"):
            for sv in detail["specValueList"]:
                if isinstance(sv, dict) and sv.get("price"):
                    price_usd = sv["price"]
                    break

        merged = {
            # Basic info
            "id": pid,
            "code": detail.get("code", ""),
            "name": name,
            "category": cat_name,
            "brand": "",

            # Pricing
            "price_usd": price_usd,
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
        time.sleep(0.25)

    print(f"\nSkipped {skipped_hand_rolled} hand-rolled tobacco products during detail fetch")
    return detailed_products


def main():
    print("=" * 70)
    print("PIPEUNCLE.COM - ALL Products (except 手卷丝) Scraper")
    print("=" * 70)

    products = scrape_all_products()

    print(f"\n{'=' * 70}")
    print(f"Scraping complete! Total products: {len(products)}")
    print(f"{'=' * 70}")

    # Save as CSV
    csv_path = os.path.join(OUTPUT_DIR, "machine_made.csv")
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
    json_path = os.path.join(OUTPUT_DIR, "machine_made.json")
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
    prices = []
    for p in products:
        try:
            price = float(p["price_usd"])
            if price > 0:
                prices.append(price)
        except (ValueError, TypeError):
            pass
    if prices:
        print(f"  Price range: ${min(prices):.2f} - ${max(prices):.2f} USD")

    # By category
    categories = {}
    for p in products:
        cat = p.get("category", "未知")
        categories[cat] = categories.get(cat, 0) + 1
    if categories:
        print(f"\n  分类分布:")
        for k, v in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")

    # By category_type
    specs = {}
    for p in products:
        s = p.get("category_type", "")
        if s:
            specs[s] = specs.get(s, 0) + 1
    if specs:
        print(f"\n  类别分布:")
        for k, v in sorted(specs.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
