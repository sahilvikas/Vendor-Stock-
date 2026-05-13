# vendor_stock/scraper/agora.py
import time
import requests
from bs4 import BeautifulSoup
from .config import AGORA_EMAIL, AGORA_PASSWORD


def scrape(log_fn=print):
    """Scrape Agora vendor portal. Returns list of product dicts."""
    log_fn("  Logging in to Agora...")
    start = time.time()

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"})

    r = session.post("https://vendor.agorafabrics.in/login_back.php", data={
        "v_email": AGORA_EMAIL, "v_password": AGORA_PASSWORD
    }, allow_redirects=True)

    if "success" not in r.url:
        raise Exception(f"Agora login failed. URL: {r.url}")

    log_fn("  Login successful, fetching products...")
    r2 = session.get("https://vendor.agorafabrics.in/view-products.php")
    soup = BeautifulSoup(r2.text, "html.parser")

    products = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) >= 6:
            try:
                stock = float(cells[5].get_text(strip=True))
            except:
                stock = 0

            products.append({
                "code": cells[2].get_text(strip=True),
                "name": cells[1].get_text(strip=True),
                "category": cells[4].get_text(strip=True),
                "stock": stock,
                "status": "IN_STOCK" if stock > 0 else "OUT_OF_STOCK"
            })

    duration = round(time.time() - start, 1)
    in_stock = sum(1 for p in products if p["stock"] > 0)
    low = sum(1 for p in products if 0 < p["stock"] < 20)

    log_fn(f"  Scraped {len(products)} products | In stock: {in_stock} | Out: {len(products) - in_stock} | Low: {low} | {duration}s")

    return {
        "products": products,
        "total": len(products),
        "in_stock": in_stock,
        "out_of_stock": len(products) - in_stock,
        "low_stock": low,
        "duration": duration
    }
