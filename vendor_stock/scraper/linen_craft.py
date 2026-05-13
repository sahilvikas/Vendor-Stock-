# vendor_stock/scraper/linen_craft.py
import time
import io
import requests
import openpyxl
from .config import LC_URL


def scrape(log_fn=print):
    """Download and parse Linen Craft SharePoint stock sheet. Returns product list."""
    log_fn("  Downloading Linen Craft sheet...")
    start = time.time()

    r = requests.get(LC_URL)
    if r.status_code != 200:
        raise Exception(f"Linen Craft download failed: HTTP {r.status_code}")

    wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)
    ws = wb.active

    stock_date = str(ws.cell(row=1, column=2).value or "")
    log_fn(f"  Stock date: {stock_date}")

    products = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        name = str(row[0] or "").strip()
        code = str(row[1] or "").strip()
        if not name or not code or "COLLECTION" in name.upper() or name == "Name":
            continue
        try:
            stock = round(float(row[3]), 2) if row[3] else 0
            committed = round(float(row[4]), 2) if row[4] else 0
            available = round(float(row[5]), 2) if row[5] else 0
        except:
            stock, committed, available = 0, 0, 0

        products.append({
            "code": code,
            "name": name,
            "width": str(row[2] or ""),
            "stock": stock,
            "committed": committed,
            "available": available,
            "status": "IN_STOCK" if available > 0 else "OUT_OF_STOCK"
        })

    duration = round(time.time() - start, 1)
    in_stock = sum(1 for p in products if p["available"] > 0)
    low = sum(1 for p in products if 0 < p["available"] < 20)

    log_fn(f"  Scraped {len(products)} products | Available: {in_stock} | Out: {len(products) - in_stock} | Low: {low} | {duration}s")

    return {
        "products": products,
        "total": len(products),
        "in_stock": in_stock,
        "out_of_stock": len(products) - in_stock,
        "low_stock": low,
        "stock_date": stock_date,
        "duration": duration
    }
