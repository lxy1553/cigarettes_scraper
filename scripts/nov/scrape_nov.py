"""
Scrape bulk pipe tobacco products from novapipesandtobacco.com (BigCommerce + Searchanise).
Output format matches other channel scrapers, with each weight variant as a separate row.
"""
import csv
import json
import os
import re
import urllib.request
import urllib.parse
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "../../data/nov"))

SEARCHANISE_API_KEY = "0R5r8h5H7Z"
SEARCHANISE_URL = "https://searchserverapi1.com/getresults"
BASE_URL = "https://novapipesandtobacco.com"
HEADERS = {"Referer": f"{BASE_URL}/"}

# Weight conversion: ounces to grams
OZ_TO_G = 28.3495


def fetch_all_products() -> list:
    """Fetch all Bulk Pipe Tobacco products via Searchanise API with pagination."""
    all_products = []
    start_index = 0
    page_size = 200

    while True:
        params = urllib.parse.urlencode({
            "api_key": SEARCHANISE_API_KEY,
            "q": "bulk",
            "maxResults": page_size,
            "startIndex": start_index,
            "items": "true",
            "categories": "true",
        })
        url = f"{SEARCHANISE_URL}?{params}"
        print(f"Fetching offset {start_index}...")

        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            cat = item.get("categories", "")
            if "Bulk Pipe Tobacco" in cat:
                all_products.append(item)

        print(f"  Got {len(items)} results, {sum(1 for i in items if 'Bulk Pipe Tobacco' in i.get('categories', ''))} bulk")
        start_index += page_size
        if len(items) < page_size:
            break
        time.sleep(0.5)

    print(f"\nTotal bulk pipe tobacco products: {len(all_products)}")
    return all_products


def parse_weight_from_options(options: dict) -> tuple:
    """Extract weight from variant options dict like {'Weight': '1 oz.'}.
    Returns (weight_in_grams, weight_in_ounces, unit) tuple.
    """
    weight_str = ""
    if isinstance(options, dict):
        weight_str = options.get("Weight", "")
    elif isinstance(options, str):
        weight_str = options

    if not weight_str:
        return (0, 0, "")

    # Match patterns like "1 oz.", "2 oz.", "16 oz.", "50g", "100 g"
    m = re.search(r"([\d.]+)\s*(oz|ounce|g|gram)s?\.?", weight_str, re.IGNORECASE)
    if m:
        value = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ("oz", "ounce"):
            grams = round(value * OZ_TO_G, 1)
            return (grams, value, "oz")
        elif unit in ("g", "gram"):
            return (value, round(value / OZ_TO_G, 2), "g")

    # Try just numbers
    m = re.search(r"([\d.]+)", weight_str)
    if m:
        grams = round(float(m.group(1)) * OZ_TO_G, 1)
        return (grams, float(m.group(1)), "oz")

    return (0, 0, "")


def extract_brand(categories: str) -> str:
    """Extract brand name from category string like 'Pipe Tobacco[:ATTR:]Bulk Pipe Tobacco[:ATTR:]Cornell & Diehl (Bulk)'"""
    parts = categories.split("[:ATTR:]")
    if len(parts) >= 3:
        brand = parts[2]
        # Clean up "(Bulk)" suffix
        brand = re.sub(r"\s*\(Bulk\)$", "", brand).strip()
        return brand
    return ""


def extract_category(categories: str) -> str:
    """Extract the main category."""
    parts = categories.split("[:ATTR:]")
    for p in parts:
        if "Bulk Pipe Tobacco" in p:
            return "bulk_pipe_tobacco"
    return "pipe_tobacco"


def extract_products(raw_products: list) -> list:
    """Convert raw API products to flat list with one row per variant."""
    results = []

    for product in raw_products:
        title = product.get("title", "").strip()
        # Remove "(Bulk)" suffix for cleaner name
        clean_title = re.sub(r"\s*\(Bulk\)$", "", title).strip()
        link = product.get("link", "")
        categories = product.get("categories", "")
        brand = extract_brand(categories)
        category = extract_category(categories)
        description = product.get("description", "")
        image = product.get("image_link", "")
        product_code = product.get("product_code", "")
        regular_price = product.get("regular_price", product.get("price", "0"))

        variants = product.get("bigcommerce_variants", [])
        if not variants:
            # No variants - single product
            results.append({
                "渠道": "nov",
                "产品名称": clean_title,
                "品牌": brand,
                "口味": "",
                "不加税价格(¥)": "",
                "单包含税价(¥)": "",
                "美元价格($)": regular_price,
                "毛重(g)": "",
                "运费(¥)": "",
                "价格/500g(¥)": "",
                "平摊运费(¥/包)": "",
                "平摊运费后烟丝成本/20支": "",
                "20支成品烟价(¥)": "",
                "规格(g)": "",
                "库存": product.get("inventory_level", ""),
                "分类": category,
                "url": link,
                "sku": product_code,
                "原始价格(USD)": regular_price,
            })
        else:
            # Each variant becomes a separate row
            for variant in variants:
                options = variant.get("options", {})
                weight_g, weight_oz, unit = parse_weight_from_options(options)
                price = variant.get("price", "0")
                list_price = variant.get("list_price", price)
                sku = variant.get("sku", "")
                available = variant.get("available", True)
                inventory = variant.get("inventory_level", "")

                # Generate a display name with weight
                if weight_g > 0:
                    display_name = f"{clean_title} ({weight_oz:.0f}oz / {weight_g:.0f}g)"
                else:
                    display_name = clean_title

                results.append({
                    "渠道": "nov",
                    "产品名称": display_name,
                    "品牌": brand,
                    "口味": "",
                    "不加税价格(¥)": "",
                    "单包含税价(¥)": "",
                    "美元价格($)": list_price,
                    "毛重(g)": weight_g,
                    "运费(¥)": "",
                    "价格/500g(¥)": "",
                    "平摊运费(¥/包)": "",
                    "平摊运费后烟丝成本/20支": "",
                    "20支成品烟价(¥)": "",
                    "规格(g)": weight_g,
                    "库存": "有货" if available else "无货",
                    "分类": category,
                    "url": link,
                    "sku": sku,
                    "原始价格(USD)": price,
                })

    print(f"Total rows (variants expanded): {len(results)}")
    return results


def save_csv(products: list, filepath: str):
    """Save products to CSV."""
    fieldnames = [
        "渠道", "产品名称", "品牌", "口味",
        "不加税价格(¥)", "单包含税价(¥)", "美元价格($)",
        "毛重(g)", "运费(¥)", "价格/500g(¥)",
        "平摊运费(¥/包)", "平摊运费后烟丝成本/20支", "20支成品烟价(¥)",
        "规格(g)", "库存", "分类",
    ]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)
    print(f"CSV saved: {filepath}")


def save_json(products: list, filepath: str):
    """Save products to JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {filepath}")


def main():
    print("=" * 70)
    print("NOVA PIPES & TOBACCO - Bulk Pipe Tobacco Scraper")
    print("=" * 70)

    raw = fetch_all_products()
    products = extract_products(raw)

    if not products:
        print("No bulk pipe tobacco products found!")
        return

    # Save
    csv_path = os.path.join(OUTPUT_DIR, "products.csv")
    json_path = os.path.join(OUTPUT_DIR, "products.json")
    save_csv(products, csv_path)
    save_json(products, json_path)

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total variants: {len(products)}")
    print(f"  Source products: {len(raw)}")

    # By brand
    brands = {}
    for p in products:
        b = p["品牌"] or "未知"
        brands[b] = brands.get(b, 0) + 1
    print(f"\n  Brands:")
    for b, c in sorted(brands.items(), key=lambda x: -x[1]):
        print(f"    {b}: {c}")

    # Price range
    prices = []
    for p in products:
        try:
            price = float(p["美元价格($)"])
            if price > 0:
                prices.append(price)
        except (ValueError, TypeError):
            pass
    if prices:
        print(f"\n  Price range: ${min(prices):.2f} - ${max(prices):.2f}")


if __name__ == "__main__":
    main()
