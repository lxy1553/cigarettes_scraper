"""
Scrape all products from ribenyan.com
Auto-detects site platform (WooCommerce, WordPress API, pipeuncle-style encrypted API, or HTML scraping)
"""
import csv
import json
import os
import re
import sys
import time
import requests
import urllib3
urllib3.disable_warnings()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://ribenyan.com"
OUTPUT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "../../data/ribenyan"))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,application/xhtml+xml,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Try to import decrypt if available (pipeuncle-style AES encryption)
sys.path.insert(0, os.path.join(_SCRIPT_DIR, "../utils"))
try:
    from decrypt import api_get as encrypted_api_get
    HAS_DECRYPT = True
except ImportError:
    HAS_DECRYPT = False


def probe_site() -> dict:
    """Probe the site to determine what platform it uses."""
    result = {"platform": "unknown", "api_endpoint": None}

    # Test 1: WooCommerce Store API
    try:
        r = requests.get(f"{BASE_URL}/wp-json/wc/store/v1/products?per_page=1", headers=HEADERS, timeout=10)
        if r.status_code == 200 and "id" in r.text:
            total = r.headers.get("X-Wp-Total", "?")
            result["platform"] = "woocommerce_store_api"
            result["api_endpoint"] = "/wp-json/wc/store/v1/products"
            result["total_products"] = int(total) if total.isdigit() else 0
            print(f"[DETECT] WooCommerce Store API - {total} products")
            return result
    except Exception:
        pass

    # Test 2: WooCommerce v3 API (maybe keyless)
    try:
        r = requests.get(f"{BASE_URL}/wp-json/wc/v3/products?per_page=1", headers=HEADERS, timeout=10)
        if r.status_code == 200 and isinstance(r.json(), list):
            total = r.headers.get("X-Wp-Total", "?")
            result["platform"] = "woocommerce_v3_api"
            result["api_endpoint"] = "/wp-json/wc/v3/products"
            result["total_products"] = int(total) if total.isdigit() else 0
            print(f"[DETECT] WooCommerce v3 API - {total} products")
            return result
    except Exception:
        pass

    # Test 3: WordPress REST API
    try:
        r = requests.get(f"{BASE_URL}/wp-json/wp/v2/product?per_page=1", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            total = r.headers.get("X-Wp-Total", "?")
            result["platform"] = "wordpress_api"
            result["api_endpoint"] = "/wp-json/wp/v2/product"
            result["total_products"] = int(total) if total.isdigit() else 0
            print(f"[DETECT] WordPress REST API - {total} products")
            return result
    except Exception:
        pass

    # Test 4: pipeuncle-style encrypted API
    if HAS_DECRYPT:
        try:
            r = encrypted_api_get(f"{BASE_URL}/api/goods/category", {})
            if r.get("code") == 200:
                result["platform"] = "encrypted_api"
                result["api_endpoint"] = "/api/goods/limit"
                print("[DETECT] Encrypted API (pipeuncle-style)")
                return result
        except Exception:
            pass

    # Test 5: Plain API
    try:
        r = requests.get(f"{BASE_URL}/api/goods/category", headers=HEADERS, timeout=10)
        if r.status_code == 200 and r.json().get("code") == 200:
            result["platform"] = "plain_api"
            result["api_endpoint"] = "/api/goods/limit"
            print("[DETECT] Plain REST API")
            return result
    except Exception:
        pass

    # Test 6: HTML - check homepage
    try:
        r = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            result["platform"] = "html"
            print("[DETECT] HTML scraping mode")
            return result
    except Exception:
        pass

    print("[ERROR] Cannot connect to site at all!")
    return result


def fetch_via_woocommerce_store_api() -> list:
    """Fetch all products via WooCommerce Store API."""
    all_products = []
    page = 1
    per_page = 100

    while True:
        print(f"  Fetching page {page}...")
        resp = requests.get(
            f"{BASE_URL}/wp-json/wc/store/v1/products",
            params={"per_page": per_page, "page": page},
            headers=HEADERS, timeout=30
        )
        if resp.status_code != 200:
            break

        if page == 1:
            total = resp.headers.get("X-Wp-Total", "?")
            print(f"  Total: {total} products")

        products = resp.json()
        if not products:
            break

        all_products.extend(products)
        page += 1
        time.sleep(0.3)

    return all_products


def fetch_via_wordpress_api() -> list:
    """Fetch via WordPress REST API."""
    all_products = []
    page = 1
    per_page = 100

    while True:
        print(f"  Fetching page {page}...")
        resp = requests.get(
            f"{BASE_URL}/wp-json/wp/v2/product",
            params={"per_page": per_page, "page": page},
            headers=HEADERS, timeout=30
        )
        if resp.status_code != 200:
            break
        if page == 1:
            total = resp.headers.get("X-Wp-Total", "?")
            print(f"  Total: {total} products")

        products = resp.json()
        if not products:
            break
        all_products.extend(products)
        page += 1
        time.sleep(0.3)

    return all_products


def fetch_via_encrypted_api() -> list:
    """Fetch via pipeuncle-style encrypted API."""
    def api_get(url, params=None):
        try:
            return encrypted_api_get(url, params) if HAS_DECRYPT else {}
        except Exception:
            return {}

    # First get all categories
    print("  Getting categories...")
    cat_result = api_get(f"{BASE_URL}/api/goods/category")
    categories_data = cat_result.get("data", [])

    all_products = []
    seen_ids = set()

    def extract_cat_ids(cats):
        ids = []
        for cat in cats:
            ids.append(cat["id"])
            if cat.get("children"):
                ids.extend(extract_cat_ids(cat["children"]))
        return ids

    all_cat_ids = extract_cat_ids(categories_data)
    print(f"  Found {len(all_cat_ids)} categories")

    for cid in all_cat_ids:
        result = api_get(f"{BASE_URL}/api/goods/limit", {"categoryId": cid, "limit": 200, "type": 1})
        products = result.get("data", [])
        new_count = 0
        for p in products:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                all_products.append(p)
                new_count += 1
        if new_count > 0:
            print(f"  Cat {cid}: +{new_count} products (total: {len(all_products)})")

    return all_products


def fetch_via_html() -> list:
    """Fetch products by scraping HTML pages."""
    all_products = []
    seen_urls = set()

    # First get homepage and find all category/product links
    print("  Scraping homepage...")
    r = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    html = r.text

    # Find category links
    cat_links = list(set(re.findall(r'href=[\'"](/product-category/[^\'"]+)[\'"]', html)))
    cat_links += list(set(re.findall(r'href=[\'"](/shop/[^\'"]+)[\'"]', html)))
    cat_links += list(set(re.findall(r'href=[\'"](/category/[^\'"]+)[\'"]', html)))
    print(f"  Found {len(cat_links)} category links")

    # Also find individual product links on homepage
    prod_links = list(set(re.findall(r'href=[\'"](/product/[^\'"]+)[\'"]', html)))
    print(f"  Found {len(prod_links)} direct product links")

    # Also check for pagination on homepage/shop page
    for page_num in range(1, 20):
        if page_num == 1:
            url = f"{BASE_URL}/shop/"
        else:
            url = f"{BASE_URL}/shop/page/{page_num}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
            new_links = list(set(re.findall(r'href=[\'"](/product/[^\'"]+)[\'"]', r.text)))
            prod_links.extend(new_links)
            if len(new_links) == 0:
                break
            print(f"  Page {page_num}: +{len(new_links)} products")
        except Exception:
            break

    all_product_urls = list(set(prod_links))
    print(f"\n  Total unique product URLs: {len(all_product_urls)}")

    for i, url in enumerate(all_product_urls):
        full_url = BASE_URL + url if url.startswith("/") else url
        print(f"  [{i+1}/{len(all_product_urls)}] {url}")
        try:
            r = requests.get(full_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                product = parse_product_html(r.text, full_url)
                if product:
                    all_products.append(product)
        except Exception as e:
            print(f"    Error: {e}")
        time.sleep(0.5)

    return all_products


def parse_product_html(html: str, url: str) -> dict:
    """Parse a product page HTML to extract details."""
    # Try to find JSON-LD structured data
    json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for jld in json_ld:
        try:
            data = json.loads(jld)
            if data.get("@type") == "Product":
                name = data.get("name", "")
                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                return {
                    "id": re.search(r'post-(\d+)', html).group(1) if re.search(r'post-(\d+)', html) else "",
                    "name": name,
                    "url": url,
                    "price": offers.get("price", ""),
                    "currency": offers.get("priceCurrency", "CNY"),
                    "in_stock": offers.get("availability", "").endswith("InStock") if offers.get("availability") else "",
                    "description": data.get("description", ""),
                    "sku": data.get("sku", ""),
                    "image": data.get("image", ""),
                    "brand": data.get("brand", {}).get("name", "") if isinstance(data.get("brand"), dict) else "",
                }
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: extract from meta tags
    title = ""
    title_match = re.search(r'<title>(.*?)</title>', html)
    if title_match:
        title = title_match.group(1).strip()

    price = ""
    price_match = re.search(r'<span[^>]*class="[^"]*price[^"]*"[^>]*>(.*?)</span>', html, re.DOTALL)
    if price_match:
        price = re.sub(r'<[^>]+>', '', price_match.group(1)).strip()

    sku = ""
    sku_match = re.search(r'SKU[:\s]*</strong>\s*([^<]+)', html)
    if not sku_match:
        sku_match = re.search(r'"sku"\s*:\s*"([^"]+)"', html)
    if sku_match:
        sku = sku_match.group(1).strip()

    return {
        "id": re.search(r'post-(\d+)', html).group(1) if re.search(r'post-(\d+)', html) else "",
        "name": title,
        "url": url,
        "price": price,
        "currency": "",
        "in_stock": "InStock" in html if "InStock" in html else "",
        "description": "",
        "sku": sku,
        "image": "",
        "brand": "",
    }


def main():
    print("=" * 70)
    print("RIBENYAN.COM - Product Scraper")
    print("=" * 70)

    # Step 1: Probe the site
    print("\nProbing site platform...")
    info = probe_site()
    print(f"  Platform: {info['platform']}")

    if info["platform"] == "unknown":
        print("\nERROR: Site is not accessible. Possible reasons:")
        print("  1. The site is geo-blocked (needs China IP)")
        print("  2. The site is behind Cloudflare anti-bot protection")
        print("  3. Network connectivity issues")
        print("\nTry running this script from a server in China or using a China proxy.")
        return

    # Step 2: Fetch products using the detected method
    raw_products = []
    if info["platform"] == "woocommerce_store_api":
        raw_products = fetch_via_woocommerce_store_api()
    elif info["platform"] == "woocommerce_v3_api":
        raw_products = fetch_via_woocommerce_store_api()  # Same approach
    elif info["platform"] == "wordpress_api":
        raw_products = fetch_via_wordpress_api()
    elif info["platform"] == "encrypted_api":
        raw_products = fetch_via_encrypted_api()
    elif info["platform"] == "plain_api":
        raw_products = fetch_via_encrypted_api()  # Same approach without decrypt
    elif info["platform"] == "html":
        raw_products = fetch_via_html()

    print(f"\nTotal products fetched: {len(raw_products)}")

    if not raw_products:
        print("No products found!")
        return

    # Step 3: Normalize products into CSV format
    products = []
    for p in raw_products:
        if isinstance(p, dict):
            # WooCommerce store API format
            prices = p.get("prices", {})
            categories = p.get("categories", [])
            images = p.get("images", [])
            product = {
                "id": p.get("id", ""),
                "sku": p.get("sku", ""),
                "name": p.get("name", ""),
                "slug": p.get("slug", ""),
                "permalink": p.get("permalink", ""),
                "type": p.get("type", ""),
                "categories": " | ".join(c.get("name", "") for c in categories),
                "price": prices.get("price", p.get("price", "")),
                "regular_price": prices.get("regular_price", ""),
                "sale_price": prices.get("sale_price", ""),
                "is_in_stock": p.get("is_in_stock", ""),
                "stock_availability": p.get("stock_availability", ""),
                "short_description": p.get("short_description", ""),
                "main_image": images[0].get("src", "") if images else "",
                "all_images": " | ".join(img.get("src", "") for img in images),
                "average_rating": p.get("average_rating", ""),
                "review_count": p.get("review_count", ""),
            }
            products.append(product)
        elif isinstance(p, str):
            products.append({"name": p, "permalink": p})

    # Step 4: Save
    csv_path = os.path.join(OUTPUT_DIR, "products.csv")
    json_path = os.path.join(OUTPUT_DIR, "products.json")

    if products:
        fieldnames = list(products[0].keys())
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(products)
        print(f"\nCSV saved: {csv_path}")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        print(f"JSON saved: {json_path}")

    # Summary
    in_stock = [p for p in products if p.get("is_in_stock")]
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(products)} products")
    print(f"  In stock: {len(in_stock)}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
