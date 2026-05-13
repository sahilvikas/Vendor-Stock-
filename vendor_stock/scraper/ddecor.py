# vendor_stock/scraper/ddecor.py
import csv
import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from .config import DDECOR_URL, DDECOR_USERNAME, DDECOR_PASSWORD, MAPPING_FILE


def kill_spinner(page):
    page.evaluate("""
        document.querySelectorAll('lightning-spinner, .slds-spinner_container').forEach(el => {
            el.style.display = 'none';
            el.remove();
        });
    """)
    time.sleep(0.3)


def cleanup_page(page):
    try:
        close_btn = page.get_by_role("button", name="close")
        if close_btn.is_visible(timeout=500):
            close_btn.click()
            time.sleep(0.3)
    except:
        pass
    for selector in [".slds-notify__close button", ".toastClose", "button[title='Close']",
                     ".slds-notify button", ".slds-notify__close"]:
        try:
            el = page.locator(selector)
            if el.count() > 0 and el.first.is_visible():
                el.first.click()
                time.sleep(0.3)
        except:
            pass
    page.evaluate("""
        document.querySelectorAll('.slds-notify_container, .slds-notify, .toastContainer').forEach(el => el.remove());
    """)
    kill_spinner(page)


def wait_for_spinner_cycle(page):
    try:
        page.locator("lightning-spinner").first.wait_for(state="visible", timeout=1500)
    except:
        time.sleep(0.5)
        return
    try:
        page.locator("lightning-spinner").first.wait_for(state="hidden", timeout=10000)
    except:
        kill_spinner(page)
    time.sleep(0.3)


def clear_field(page, field_name):
    try:
        clear_btns = page.locator("button.slds-combobox__input-entity-icon")
        for i in range(clear_btns.count()):
            if clear_btns.nth(i).is_visible():
                clear_btns.nth(i).click()
                time.sleep(0.3)
                wait_for_spinner_cycle(page)
    except:
        pass
    try:
        field = page.get_by_role("searchbox", name=field_name)
        field.click()
        time.sleep(0.2)
        field.press("Control+a")
        time.sleep(0.1)
        field.press("Backspace")
        time.sleep(0.3)
        wait_for_spinner_cycle(page)
    except:
        pass


def find_in_dropdown(page, target_text):
    target_upper = target_text.upper().strip()
    try:
        options = page.locator("[role='listbox'] [role='option'], .slds-listbox__item")
        count = options.count()
        if count == 0:
            options = page.locator("span").filter(has_text=target_upper.split()[0] if target_upper else "")
            count = options.count()

        option_texts = []
        for i in range(min(count, 20)):
            try:
                el = options.nth(i)
                if el.is_visible():
                    txt = el.inner_text().strip().upper()
                    if txt and txt != "NO RESULTS FOUND" and len(txt) > 1:
                        option_texts.append((txt, i))
            except:
                continue

        if not option_texts:
            return None

        for txt, idx in option_texts:
            if txt == target_upper:
                options.nth(idx).click(timeout=2000)
                time.sleep(0.5)
                wait_for_spinner_cycle(page)
                return txt

        matches = []
        for txt, idx in option_texts:
            if txt in target_upper or target_upper.startswith(txt):
                matches.append((len(txt), txt, idx))
        if matches:
            matches.sort(reverse=True)
            _, best_txt, best_idx = matches[0]
            options.nth(best_idx).click(timeout=2000)
            time.sleep(0.5)
            wait_for_spinner_cycle(page)
            return best_txt
    except:
        pass

    try:
        match = page.locator("span").filter(has_text=target_upper)
        for nth in [1, 0, 2]:
            if nth < match.count():
                try:
                    el = match.nth(nth)
                    if el.is_visible():
                        el.click(timeout=2000)
                        time.sleep(0.5)
                        wait_for_spinner_cycle(page)
                        return target_upper
                except:
                    continue
    except:
        pass
    return None


def type_and_select(page, field_name, target_text):
    clear_field(page, field_name)
    time.sleep(0.3)
    field = page.get_by_role("searchbox", name=field_name)
    field.click()
    time.sleep(0.5)

    for i, char in enumerate(target_text.lower()):
        page.keyboard.type(char)
        page.keyboard.press("Enter")
        wait_for_spinner_cycle(page)
        matched = find_in_dropdown(page, target_text)
        if matched:
            return matched
        if i >= 10:
            break

    time.sleep(1)
    return find_in_dropdown(page, target_text)


def select_serial(page, serial):
    clear_field(page, "Serial Number")
    time.sleep(0.3)
    field = page.get_by_role("searchbox", name="Serial Number")
    field.click()
    time.sleep(0.3)

    for char in serial:
        page.keyboard.type(char)
        page.keyboard.press("Enter")
        wait_for_spinner_cycle(page)

    time.sleep(1)

    try:
        page.get_by_text(serial, exact=True).click(timeout=3000)
        time.sleep(0.5)
        wait_for_spinner_cycle(page)
        return True
    except:
        pass

    for nth in [1, 2, 0, 3]:
        try:
            page.locator("span").filter(has_text=serial).nth(nth).click(timeout=2000)
            time.sleep(0.5)
            wait_for_spinner_cycle(page)
            return True
        except:
            continue
    return False


def read_popup(page):
    data = {
        "total_stock": "", "price": "",
        "tarapur_lt10": "", "tarapur_10_30": "", "tarapur_gt30": "",
        "noida_lt10": "", "noida_10_30": "", "noida_gt30": "",
        "bangalore_lt10": "", "bangalore_10_30": "", "bangalore_gt30": "",
    }
    try:
        stock_el = page.locator("text=Total Stock").first
        if stock_el.is_visible():
            data["total_stock"] = stock_el.inner_text().split(":")[-1].strip()
    except:
        pass
    try:
        price_el = page.locator("text=/Rs \\d+/").first
        if price_el.is_visible():
            data["price"] = price_el.inner_text().strip()
    except:
        pass
    try:
        table_rows = page.locator("tr")
        for i in range(table_rows.count()):
            row_text = table_rows.nth(i).inner_text()
            cells = row_text.split("\t")
            if len(cells) >= 4:
                label = cells[0].strip().lower()
                if "less" in label:
                    data["tarapur_lt10"] = cells[1].strip()
                    data["noida_lt10"] = cells[2].strip()
                    data["bangalore_lt10"] = cells[3].strip()
                elif "between" in label:
                    data["tarapur_10_30"] = cells[1].strip()
                    data["noida_10_30"] = cells[2].strip()
                    data["bangalore_10_30"] = cells[3].strip()
                elif "more" in label:
                    data["tarapur_gt30"] = cells[1].strip()
                    data["noida_gt30"] = cells[2].strip()
                    data["bangalore_gt30"] = cells[3].strip()
    except:
        pass
    return data


def check_stock(page, collection, serial, collection_already_selected=False):
    result = {
        "collection_searched": collection, "serial_searched": serial,
        "status": "ERROR", "product_name": "",
        "total_stock": "", "price": "",
        "tarapur_lt10": "", "tarapur_10_30": "", "tarapur_gt30": "",
        "noida_lt10": "", "noida_10_30": "", "noida_gt30": "",
        "bangalore_lt10": "", "bangalore_10_30": "", "bangalore_gt30": "",
        "error": ""
    }
    try:
        if not collection_already_selected:
            matched = type_and_select(page, "Collection", collection)
            if not matched:
                result["status"] = "COLLECTION_NOT_FOUND"
                result["error"] = f"'{collection}' not in dropdown"
                return result
            if matched != collection.upper():
                result["product_name"] = f"Matched as: {matched}"

        if not select_serial(page, serial):
            result["status"] = "SERIAL_NOT_FOUND"
            result["error"] = f"Serial '{serial}' not in dropdown"
            return result

        qty_field = page.get_by_role("textbox", name="Quantity")
        qty_field.click()
        qty_field.fill("1")
        time.sleep(0.3)

        page.get_by_role("button", name="Check").click()
        time.sleep(3)
        wait_for_spinner_cycle(page)
        time.sleep(1)

        if page.locator("text=discontinued Product").count() > 0:
            result["status"] = "DISCONTINUED"
            cleanup_page(page)
            return result

        stock_el = page.locator("text=Total Stock")
        if stock_el.count() > 0 and stock_el.first.is_visible():
            popup_data = read_popup(page)
            result.update(popup_data)
            total = 0
            try:
                total = float(result["total_stock"])
            except:
                pass
            result["status"] = "IN_STOCK" if total > 0 else "OUT_OF_STOCK"
            try:
                page.get_by_role("button", name="close").click()
            except:
                pass
            time.sleep(0.5)
            kill_spinner(page)
        else:
            stock_loc = page.locator("text=Stock is available on Location")
            if stock_loc.count() > 0 and stock_loc.first.is_visible():
                try:
                    loc_text = stock_loc.first.inner_text().strip()
                    result["error"] = loc_text
                except:
                    pass
                try:
                    page.get_by_text("Stock Details").click(timeout=3000)
                    time.sleep(3)
                    wait_for_spinner_cycle(page)
                    stock_el2 = page.locator("text=Total Stock")
                    if stock_el2.count() > 0 and stock_el2.first.is_visible():
                        popup_data = read_popup(page)
                        result.update(popup_data)
                        total = 0
                        try:
                            total = float(result["total_stock"])
                        except:
                            pass
                        result["status"] = "IN_STOCK" if total > 0 else "OUT_OF_STOCK"
                        result["error"] = loc_text
                        try:
                            page.get_by_role("button", name="close").click()
                        except:
                            pass
                        time.sleep(0.5)
                        kill_spinner(page)
                    else:
                        result["status"] = "IN_STOCK"
                except:
                    result["status"] = "IN_STOCK"
            elif page.locator("text=Stock is not available").count() > 0:
                result["status"] = "OUT_OF_STOCK"
                result["error"] = "Stock is not available"
            else:
                result["status"] = "NO_POPUP"
                result["error"] = "No popup or message appeared"

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)[:200]
        try:
            page.reload()
            page.wait_for_selector("text=Fabric Stock Check", timeout=20000)
            time.sleep(2)
            kill_spinner(page)
        except:
            pass
    return result


def load_mapping():
    """Load DDécor mapping TSV"""
    items = []
    if not os.path.exists(MAPPING_FILE):
        raise Exception(f"Mapping file not found: {MAPPING_FILE}")

    with open(MAPPING_FILE, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("STATUS") == "AUTO" and row.get("COLLECTION") and row.get("SERIAL"):
                items.append(row)
    return items


def scrape(log_fn=print, max_items=None):
    """Scrape DDécor portal. Returns list of result dicts."""
    items = load_mapping()
    items.sort(key=lambda x: (x["COLLECTION"], x["SERIAL"]))

    if max_items:
        items = items[:max_items]

    log_fn(f"  Checking {len(items)} items...")
    start = time.time()
    results = []

    # CSV for crash recovery
    scraper_dir = os.path.dirname(os.path.abspath(__file__))
    recovery_csv = os.path.join(scraper_dir, f"logs/ddecor_recovery_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    os.makedirs(os.path.dirname(recovery_csv), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # login
        log_fn("  Logging in to DDécor...")
        page.goto(DDECOR_URL)
        page.get_by_role("textbox", name="Username").fill(DDECOR_USERNAME)
        page.get_by_role("textbox", name="Password").fill(DDECOR_PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_selector("text=Fabric Stock Check", timeout=30000)
        time.sleep(2)
        kill_spinner(page)
        log_fn("  Login successful")

        last_collection = None

        for idx, item in enumerate(items):
            collection = item["COLLECTION"]
            serial = item["SERIAL"]
            same_collection = (collection == last_collection)

            if not same_collection:
                log_fn(f"  --- {collection} ---")

            log_fn(f"    [{idx+1}/{len(items)}] Sr {serial}" + (" (same)" if same_collection else ""))

            result = check_stock(page, collection, serial, collection_already_selected=same_collection)
            cleanup_page(page)

            result["item_code"] = item["ITEM_CODE"]
            result["item_name"] = item["ITEM_NAME"]
            result["supplier"] = item["SUPPLIER"]

            icon = {"IN_STOCK": "✓", "OUT_OF_STOCK": "✗", "DISCONTINUED": "⊘",
                    "COLLECTION_NOT_FOUND": "?C", "SERIAL_NOT_FOUND": "?S"}.get(result["status"], "!")
            extra = ""
            if result["total_stock"]:
                extra += f" Stock:{result['total_stock']}"
            if result["price"]:
                extra += f" {result['price']}"
            if result["error"]:
                extra += f" | {result['error'][:60]}"
            log_fn(f"      {icon} {result['status']}{extra}")

            if result["status"] in ("IN_STOCK", "OUT_OF_STOCK"):
                last_collection = collection
            else:
                last_collection = None
                try:
                    page.reload()
                    page.wait_for_selector("text=Fabric Stock Check", timeout=20000)
                    time.sleep(2)
                    kill_spinner(page)
                except:
                    pass

            results.append(result)

            # save recovery CSV after every item
            fieldnames = ["item_code", "item_name", "supplier", "collection_searched", "serial_searched",
                          "status", "product_name", "total_stock", "price",
                          "tarapur_lt10", "tarapur_10_30", "tarapur_gt30",
                          "noida_lt10", "noida_10_30", "noida_gt30",
                          "bangalore_lt10", "bangalore_10_30", "bangalore_gt30", "error"]
            with open(recovery_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)

        browser.close()

    duration = round(time.time() - start, 1)
    statuses = {}
    for r in results:
        s = r.get("status", "UNKNOWN")
        statuses[s] = statuses.get(s, 0) + 1

    log_fn(f"  DONE - {len(results)} items in {round(duration/60, 1)} mins")
    for s, c in sorted(statuses.items()):
        log_fn(f"    {s}: {c}")

    return {
        "results": results,
        "total": len(results),
        "in_stock": statuses.get("IN_STOCK", 0),
        "out_of_stock": statuses.get("OUT_OF_STOCK", 0),
        "discontinued": statuses.get("DISCONTINUED", 0),
        "collection_not_found": statuses.get("COLLECTION_NOT_FOUND", 0),
        "serial_not_found": statuses.get("SERIAL_NOT_FOUND", 0),
        "errors": statuses.get("ERROR", 0),
        "low_stock": sum(1 for r in results if r.get("total_stock") and 0 < float(r["total_stock"]) < 20),
        "duration": duration
    }
