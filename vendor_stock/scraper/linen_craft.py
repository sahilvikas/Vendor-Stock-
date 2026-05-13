# vendor_stock/scraper/linen_craft.py
import re
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


def match_erp_to_lc(erp_item_name, products):
    """
    Match an ERP item to a Linen Craft product using multiple strategies:
    1. Keyword overlap (splitting on spaces AND dashes)
    2. Fabric code fallback (extract numeric code from ERP name, match to LC code)

    Returns (best_match, score) or (None, 0)
    """
    # Strategy 1: Keyword overlap with dash-splitting
    erp_words = set(w.upper() for w in re.split(r'[\s\-]+', erp_item_name) if len(w) > 2)
    best_match = None
    best_score = 0

    for p in products:
        sheet_words = set(w.upper() for w in re.split(r'[\s\-]+', p["name"]) if len(w) > 2)
        score = len(erp_words & sheet_words)
        if score > best_score:
            best_score = score
            best_match = p

    if best_match and best_score >= 2:
        return best_match, best_score

    # Strategy 2: Fabric code fallback
    # Extract potential fabric codes from the ERP item name
    # Patterns: "5489-0000", "8060-0000", "48031-0000", "SJAWA 5453", "F029", "P012", "10104"
    code_patterns = re.findall(r'\b(\d{4,5})\b', erp_item_name)

    if code_patterns:
        for fabric_code in code_patterns:
            for p in products:
                lc_code_clean = p["code"].replace(" ", "")
                if fabric_code == lc_code_clean:
                    return p, 1  # score 1 = code match

            # Also try with "SJAWA" prefix for waterproof items
            for p in products:
                lc_code_clean = p["code"].replace(" ", "")
                if "SJAWA" + fabric_code == lc_code_clean:
                    return p, 1

    # Strategy 3: Short alpha codes like F029, P012
    alpha_codes = re.findall(r'\b([A-Z]\d{3})\b', erp_item_name.upper())
    for ac in alpha_codes:
        for p in products:
            if ac in p["code"].replace(" ", "").upper():
                return p, 1

    return None, 0
