# vendor_stock/scraper/sarom.py
"""
Sarom Stock Scraper

Sarom sends "Sarom Stock Details" emails from order@sarom.info to
etsy@cozycornerpatios.com every few days with ~18 XLS attachments
(one per collection: ABELLONE.xls, CASSIA.xls, etc.)

This module:
1. Connects to Gmail via IMAP
2. Finds the latest Sarom email (newer than last processed)
3. Downloads all .xls attachments → sarom_data/
4. Parses the stock files
5. Matches to ERP items using collection + serial mapping
"""
import os
import re
import json
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

from .config import (
    SAROM_IMAP_HOST,
    SAROM_IMAP_EMAIL,
    SAROM_IMAP_PASSWORD,
    SAROM_SENDER,
    SAROM_SUBJECT,
)

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
SAROM_DIR = os.path.join(SCRAPER_DIR, "sarom_data")
MARKER_FILE = os.path.join(SCRAPER_DIR, "logs", "sarom_last_email.json")


# ==========================================
# 1. EMAIL - Check Gmail for new Sarom stock
# ==========================================

def _decode_header_value(value):
    """Decode email header value."""
    if value is None:
        return ""
    decoded_parts = decode_header(value)
    result = ""
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += part
    return result


def _get_last_processed():
    """Read the marker file to get the last processed email UID and date."""
    if os.path.exists(MARKER_FILE):
        try:
            with open(MARKER_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"uid": None, "date": None, "message_id": None}


def _save_last_processed(uid, date_str, message_id):
    """Save marker so we don't reprocess the same email."""
    os.makedirs(os.path.dirname(MARKER_FILE), exist_ok=True)
    with open(MARKER_FILE, "w") as f:
        json.dump({
            "uid": uid,
            "date": date_str,
            "message_id": message_id,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)


def check_email(log_fn=print):
    """
    Connect to Gmail via IMAP, find the latest Sarom stock email.
    Returns:
        dict with "found", "uid", "date", "attachments_count"
        or None if no new email
    """
    log_fn("  Connecting to Gmail (IMAP)...")

    mail = imaplib.IMAP4_SSL(SAROM_IMAP_HOST)
    mail.login(SAROM_IMAP_EMAIL, SAROM_IMAP_PASSWORD)
    mail.select("INBOX")

    # Search for emails from Sarom with the expected subject
    # Search by FROM + SUBJECT
    search_criteria = f'(FROM "{SAROM_SENDER}" SUBJECT "{SAROM_SUBJECT}")'
    status, data = mail.search(None, search_criteria)

    if status != "OK" or not data[0]:
        log_fn("  No Sarom emails found")
        mail.logout()
        return None

    email_ids = data[0].split()
    log_fn(f"  Found {len(email_ids)} Sarom email(s)")

    # Get the latest one (last in list)
    latest_id = email_ids[-1]

    # Fetch the email
    status, msg_data = mail.fetch(latest_id, "(RFC822 UID)")

    # Extract UID from response
    uid = None
    for part in msg_data:
        if isinstance(part, tuple):
            uid_match = re.search(rb"UID (\d+)", part[0])
            if uid_match:
                uid = uid_match.group(1).decode()

    # Parse the email
    raw_email = None
    for part in msg_data:
        if isinstance(part, tuple):
            raw_email = part[1]
            break

    if not raw_email:
        log_fn("  Could not fetch email content")
        mail.logout()
        return None

    msg = email.message_from_bytes(raw_email)
    message_id = msg.get("Message-ID", "")
    email_date = msg.get("Date", "")
    subject = _decode_header_value(msg.get("Subject", ""))

    log_fn(f"  Latest email: {subject}")
    log_fn(f"  Date: {email_date}")
    log_fn(f"  Message-ID: {message_id}")

    # Check if already processed
    last = _get_last_processed()
    if last.get("message_id") and last["message_id"] == message_id:
        log_fn("  Already processed this email, skipping")
        mail.logout()
        return {"found": False, "reason": "already_processed"}

    # Download attachments
    attachments = []
    os.makedirs(SAROM_DIR, exist_ok=True)

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue

        filename = part.get_filename()
        if filename:
            filename = _decode_header_value(filename)
            if filename.lower().endswith(".xls"):
                filepath = os.path.join(SAROM_DIR, filename)
                content = part.get_payload(decode=True)
                if content:
                    with open(filepath, "wb") as f:
                        f.write(content)
                    attachments.append(filename)
                    log_fn(f"    Saved: {filename} ({len(content)} bytes)")

    log_fn(f"  Downloaded {len(attachments)} XLS files")

    # Save marker
    _save_last_processed(uid, email_date, message_id)

    mail.logout()

    return {
        "found": True,
        "uid": uid,
        "date": email_date,
        "message_id": message_id,
        "attachments": attachments,
        "attachments_count": len(attachments),
    }


# ==========================================
# 2. PARSE - Read XLS files from sarom_data
# ==========================================

def parse_stock_files(log_fn=print):
    """
    Parse all .xls files in sarom_data/.
    Returns list of stock dicts.
    """
    stock_data = []

    if not os.path.exists(SAROM_DIR):
        log_fn("  sarom_data/ directory not found")
        return stock_data

    xls_files = sorted([f for f in os.listdir(SAROM_DIR) if f.endswith(".xls")])
    log_fn(f"  Parsing {len(xls_files)} XLS files...")

    for fname in xls_files:
        filepath = os.path.join(SAROM_DIR, fname)
        try:
            content = open(filepath, "r", encoding="utf-8", errors="replace").read()
        except Exception as e:
            log_fn(f"    Error reading {fname}: {e}")
            continue

        file_count = 0
        for line in content.strip().split("\n"):
            line = line.replace('"', '').strip()
            if not line or line.startswith("Collection"):
                continue
            parts = line.split("\t")
            if len(parts) >= 4:
                stock_text = parts[2].strip().upper()

                if "NOT AVAILABLE" in stock_text:
                    status = "OUT_OF_STOCK"
                elif "AVAILABLE IN PIECE" in stock_text:
                    status = "LOW_STOCK"
                elif "AVAILABLE" in stock_text:
                    status = "IN_STOCK"
                else:
                    status = "UNKNOWN"

                edd = parts[3].strip() if len(parts) > 3 and parts[3].strip() != "-" else ""

                stock_data.append({
                    "file": fname.replace(".xls", ""),
                    "collection": parts[0].strip().upper(),
                    "serial": parts[1].strip(),
                    "stock_text": parts[2].strip(),
                    "status": status,
                    "edd": edd,
                })
                file_count += 1

        log_fn(f"    {fname}: {file_count} items")

    log_fn(f"  Total stock items parsed: {len(stock_data)}")
    return stock_data


# ==========================================
# 3. MATCH - Map stock data to ERP items
# ==========================================

def match_to_erp(stock_data, erp_items, log_fn=print):
    """
    Match Sarom stock data to ERP items using the multi-strategy
    matching algorithm (direct, underscore, cross-ref, etc.)

    Args:
        stock_data: list of parsed stock dicts
        erp_items: list of ERP item dicts with item_code + item_name

    Returns:
        (matched, unmatched) tuple
    """
    log_fn(f"  Matching {len(stock_data)} stock items to {len(erp_items)} ERP items...")

    # Build lookup keys
    erp_lookup = {}
    for item in erp_items:
        name_upper = item.item_name.upper()
        clean = re.sub(r'[^A-Z0-9\s]', ' ', name_upper)
        clean = re.sub(r'\s+', ' ', clean).strip()
        clean = re.sub(r'^A\s+SAROM\s+', '', clean)
        clean = re.sub(r'^PG\s+NO?\s+\d+\s+', '', clean)

        words = clean.split()

        if len(words) >= 2 and words[-1].isdigit():
            serial_val = words[-1]
            collection = " ".join(words[:-1])

            # full collection|serial
            erp_lookup[f"{collection}|{serial_val}"] = item

            # each word|serial
            for w in words[:-1]:
                if w not in ("A", "SAROM", "PG", "NO"):
                    key = f"{w}|{serial_val}"
                    if key not in erp_lookup:
                        erp_lookup[key] = item

            # KEIBA offset: ERP serial 1-21 -> Sarom serial 901-921
            if "KEIBA" in collection:
                offset_serial = str(int(serial_val) + 900)
                erp_lookup[f"KEIBA|{offset_serial}"] = item

            # FLOROUS -> DIGITAL PRINT cross-ref
            if "FLOROUS" in collection:
                erp_lookup[f"DIGITAL PRINT|{serial_val}"] = item

    log_fn(f"  Built {len(erp_lookup)} lookup keys")

    # Match each stock item
    matched = []
    unmatched = []

    for s in stock_data:
        col = s["collection"]
        serial = s["serial"].strip()
        status = s["status"]

        erp_item = None
        match_method = ""

        # 1. Direct: COLLECTION|SERIAL
        erp_item = erp_lookup.get(f"{col}|{serial}")
        if erp_item:
            match_method = "direct"

        # 2. VIVIAN_CHECKS -> VIVIAN CHECKS
        if not erp_item:
            erp_item = erp_lookup.get(f"{col.replace('_', ' ')}|{serial}")
            if erp_item:
                match_method = "underscore"

        # 3. Cross-ref: "CASSIA-114" or "AFRO - 101" or "DIGITAL PRINT-101"
        if not erp_item and ("-" in serial or " - " in serial):
            # Normalize " - " to "-" but keep spaces within names
            normalized = serial.replace(" - ", "-").strip()
            last_dash = normalized.rfind("-")
            if last_dash > 0:
                sub_col = normalized[:last_dash].strip().upper()
                sub_serial = normalized[last_dash + 1:].strip()
            else:
                sub_col = ""
                sub_serial = ""
            if sub_col and sub_serial:

                # Try sub_col|sub_serial
                erp_item = erp_lookup.get(f"{sub_col}|{sub_serial}")
                if erp_item:
                    match_method = "cross-ref"

                # Try PIANO sub_col|sub_serial
                if not erp_item:
                    erp_item = erp_lookup.get(f"PIANO {sub_col}|{sub_serial}")
                    if erp_item:
                        match_method = "piano-sub"

                # Try FILE_NAME sub_col|sub_serial
                if not erp_item:
                    erp_item = erp_lookup.get(f"{col} {sub_col}|{sub_serial}")
                    if erp_item:
                        match_method = "file-sub"

        # 4. Handle "LUKE-N 107" style (dash then space then number)
        if not erp_item and "-" in serial:
            m = re.match(r'^([A-Z]+)-?([A-Z]*)\s+(\d+)$', serial, re.IGNORECASE)
            if m:
                sub_name = (m.group(1) + " " + m.group(2)).strip()
                sub_serial = m.group(3)
                erp_item = erp_lookup.get(f"{sub_name}|{sub_serial}")
                if erp_item:
                    match_method = "dash-space"

        if erp_item:
            matched.append({
                "item_code": erp_item.item_code,
                "item_name": erp_item.item_name,
                "collection": col,
                "serial": serial,
                "status": status,
                "edd": s["edd"],
                "method": match_method,
            })
        else:
            unmatched.append({
                "collection": col,
                "serial": serial,
                "status": status,
                "edd": s["edd"],
            })

    # Log summary
    col_stats = {}
    for m in matched:
        c = m["collection"]
        if c not in col_stats:
            col_stats[c] = {"total": 0, "in": 0, "out": 0, "low": 0}
        col_stats[c]["total"] += 1
        if m["status"] == "IN_STOCK":
            col_stats[c]["in"] += 1
        elif m["status"] == "OUT_OF_STOCK":
            col_stats[c]["out"] += 1
        elif m["status"] == "LOW_STOCK":
            col_stats[c]["low"] += 1

    log_fn(f"  Matched: {len(matched)} | Unmatched: {len(unmatched)}")
    for col in sorted(col_stats.keys()):
        s = col_stats[col]
        log_fn(f"    {col:<20} {s['total']:>4} items | In:{s['in']} Out:{s['out']} Piece:{s['low']}")

    if unmatched:
        col_missing = {}
        for u in unmatched:
            c = u["collection"]
            col_missing[c] = col_missing.get(c, 0) + 1
        log_fn(f"  Unmatched by collection:")
        for c in sorted(col_missing.keys()):
            log_fn(f"    {c}: {col_missing[c]}")

    return matched, unmatched


# ==========================================
# 4. SCRAPE - Main entry point
# ==========================================

def scrape(log_fn=print):
    """
    Full Sarom scrape flow:
    1. Check Gmail for new stock email
    2. Download attachments if new
    3. Parse XLS files
    4. Match to ERP items
    Returns dict compatible with other scrapers.
    """
    import time
    start = time.time()

    # Step 1: Check for new email
    log_fn("  Checking for new Sarom stock email...")
    email_result = None
    new_email = False

    try:
        email_result = check_email(log_fn=log_fn)
        if email_result and email_result.get("found"):
            new_email = True
            log_fn(f"  New email found with {email_result['attachments_count']} attachments")
        elif email_result and email_result.get("reason") == "already_processed":
            log_fn("  No new email, using existing sarom_data/ files")
        else:
            log_fn("  No Sarom emails found, using existing sarom_data/ files")
    except Exception as e:
        log_fn(f"  Email check failed: {e}")
        log_fn("  Falling back to existing sarom_data/ files")

    # Step 2: Parse stock files (new or existing)
    stock_data = parse_stock_files(log_fn=log_fn)

    if not stock_data:
        duration = round(time.time() - start, 1)
        return {
            "matched": [],
            "unmatched": [],
            "total": 0,
            "in_stock": 0,
            "out_of_stock": 0,
            "low_stock": 0,
            "new_email": new_email,
            "duration": duration,
            "error": "No stock data found",
        }

    # Step 3: Get ERP items with Sarom as supplier
    # Note: frappe must be initialized before calling this
    import frappe
    erp_items = frappe.db.sql("""
        SELECT i.name as item_code, i.item_name
        FROM `tabItem` i
        JOIN `tabItem Default` id ON id.parent = i.name
        WHERE id.default_supplier LIKE '%%Sarom%%'
        AND i.disabled = 0
    """, as_dict=1)

    log_fn(f"  ERP Sarom items: {len(erp_items)}")

    # Step 4: Match
    matched, unmatched = match_to_erp(stock_data, erp_items, log_fn=log_fn)

    duration = round(time.time() - start, 1)

    in_stock = sum(1 for m in matched if m["status"] == "IN_STOCK")
    out_of_stock = sum(1 for m in matched if m["status"] == "OUT_OF_STOCK")
    low_stock = sum(1 for m in matched if m["status"] == "LOW_STOCK")

    log_fn(f"  DONE - {len(matched)} matched, {len(unmatched)} unmatched in {duration}s")

    return {
        "matched": matched,
        "unmatched": unmatched,
        "total": len(matched),
        "in_stock": in_stock,
        "out_of_stock": out_of_stock,
        "low_stock": low_stock,
        "new_email": new_email,
        "email_date": email_result.get("date", "") if email_result else "",
        "stock_items_parsed": len(stock_data),
        "erp_items_found": len(erp_items),
        "duration": duration,
    }
