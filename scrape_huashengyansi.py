"""
Scrape all products from huashengyansi.cv using WooCommerce Store API.
"""
import csv
import json
import os
import time
import requests

BASE_URL = "https://www.huashengyansi.cv"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def fetch_all_products() -> list:
    """Fetch all products via WooCommerce Store API with pagination."""
    all_products = []
    page = 1
    per_page = 100

    while True:
        print(f"Fetching page {page}...")
        resp = requests.get(
            f"{BASE_URL}/wp-json/wc/store/v1/products",
            params={"per_page": per_page, "page": page},
            headers=HEADERS,
            timeout=30
        )
        resp.raise_for_status()

        # Check total from headers on first request
        if page == 1:
            total = int(resp.headers.get("X-Wp-Total", 0))
            total_pages = int(resp.headers.get("X-Wp-Totalpages", 0))
            print(f"  Total products: {total}, Total pages: {total_pages}")

        products = resp.json()
        if not products:
            break

        print(f"  Got {len(products)} products")
        all_products.extend(products)
        page += 1
        time.sleep(0.3)

    print(f"\nTotal products fetched: {len(all_products)}")
    return all_products


def extract_product_data(product: dict) -> dict:
    """Extract structured data from a WooCommerce Store API product."""
    prices = product.get("prices", {})

    # Categories
    categories = product.get("categories", [])
    cat_names = " | ".join(c.get("name", "") for c in categories)

    # Images
    images = product.get("images", [])
    image_urls = []
    for img in images:
        image_urls.append(img.get("src", ""))
    main_image = image_urls[0] if image_urls else ""

    # Attributes
    attrs = product.get("attributes", [])
    attr_strs = []
    for attr in attrs:
        name = attr.get("name", "")
        terms = attr.get("terms", []) or []
        # terms can be list of dicts or list of strings
        if terms and isinstance(terms[0], dict):
            term_values = ", ".join(t.get("name", "") for t in terms)
        else:
            term_values = ", ".join(str(t) for t in terms)
        if name:
            attr_strs.append(f"{name}: {term_values}")
    attributes_str = " | ".join(attr_strs)

    # Stock
    stock_status = product.get("stock_availability", "")
    is_in_stock = product.get("is_in_stock", False)

    return {
        "id": product.get("id", ""),
        "sku": product.get("sku", ""),
        "name": product.get("name", ""),
        "slug": product.get("slug", ""),
        "permalink": product.get("permalink", ""),
        "type": product.get("type", ""),

        # Categories
        "categories": cat_names,

        # Pricing
        "price": prices.get("price", ""),
        "regular_price": prices.get("regular_price", ""),
        "sale_price": prices.get("sale_price", ""),
        "currency": f"{prices.get('currency_prefix', '')}{prices.get('currency_code', '')}",
        "on_sale": product.get("on_sale", False),

        # Stock
        "is_in_stock": is_in_stock,
        "stock_availability": stock_status,
        "low_stock_remaining": product.get("low_stock_remaining", ""),

        # Content
        "short_description": product.get("short_description", ""),
        "description": product.get("description", ""),

        # Rating
        "average_rating": product.get("average_rating", ""),
        "review_count": product.get("review_count", ""),

        # Images
        "main_image": main_image,
        "all_images": " | ".join(image_urls),

        # Attributes
        "attributes": attributes_str,

        # Misc
        "is_purchasable": product.get("is_purchasable", False),
        "has_options": product.get("has_options", False),
    }


def main():
    print("=" * 70)
    print("HUASHENGYANSI.CV - All Products Scraper")
    print("=" * 70)

    raw_products = fetch_all_products()
    products = [extract_product_data(p) for p in raw_products]

    # Save CSV
    csv_path = os.path.join(OUTPUT_DIR, "huashengyansi_products.csv")
    fieldnames = [
        "id", "sku", "name", "slug", "permalink", "type",
        "categories",
        "price", "regular_price", "sale_price", "currency", "on_sale",
        "is_in_stock", "stock_availability", "low_stock_remaining",
        "short_description", "description",
        "average_rating", "review_count",
        "main_image", "all_images",
        "attributes",
        "is_purchasable", "has_options",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)
    print(f"\nCSV saved: {csv_path}")

    # Save JSON
    json_path = os.path.join(OUTPUT_DIR, "huashengyansi_products.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {json_path}")

    # Summary
    in_stock = [p for p in products if p["is_in_stock"]]
    out_stock = [p for p in products if not p["is_in_stock"]]

    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total products: {len(products)}")
    print(f"  In stock: {len(in_stock)}")
    print(f"  Out of stock: {len(out_stock)}")

    # By type
    types = {}
    for p in products:
        t = p["type"]
        types[t] = types.get(t, 0) + 1
    print(f"\n  Product types:")
    for t, c in sorted(types.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # By category
    cats = {}
    for p in products:
        for cat in p["categories"].split(" | "):
            cat = cat.strip()
            if cat:
                cats[cat] = cats.get(cat, 0) + 1
    print(f"\n  Top categories:")
    for cat, c in sorted(cats.items(), key=lambda x: -x[1])[:20]:
        print(f"    {cat}: {c}")

    # Price range
    prices = []
    for p in products:
        try:
            price = float(p["price"])
            if price > 0:
                prices.append(price)
        except (ValueError, TypeError):
            pass
    if prices:
        print(f"\n  Price range: ¥{min(prices):.2f} - ¥{max(prices):.2f}")


if __name__ == "__main__":
    main()
