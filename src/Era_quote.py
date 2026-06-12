"""
ERA Power — Quote & Sales Order Module
=======================================
Screen 2525

Two flows — only difference is PQ at the start for quotes:

  SALES ORDER flow:
    2525 + Enter
    make code + Enter
    Enter  (skip invoice#)
    customer id + Enter
    Enter  (skip field after customer)
    Enter  (skip order type)
    part# + Enter  → qty + Enter  (repeat for all parts)
    Enter  (done with parts)
    E + Enter
    E + Enter
    → read screen → save to JSON
    S + Enter  (save)
    NOTE: counterman is NOT set in sales flow — field is pre-filled/skipped

  QUOTE flow:
    2525 + Enter
    make code + Enter
    PQ + Enter  ← only difference
    Enter  (skip quote#)
    customer id + Enter
    Enter  (skip field)
    counterman if provided else Enter
    Enter  (skip order type)
    part# + Enter  → qty + Enter  (repeat for all parts)
    Enter  (done with parts)
    E + Enter
    E + Enter
    → read screen → save to JSON
    S + Enter  (save)
"""

import re
import time
import json
import logging
from pywinauto.keyboard import send_keys

from Era_power import (
    find_era_window,
    launch_era_port,
    login,
    logoff_era,
    read_screen_text,
    navigate_to,
    wait_for_text,
    WAIT_SHORT,
    WAIT_MEDIUM,
    WAIT_LONG,
)

log = logging.getLogger("eraPower.quote")

OUTPUT_FILE = r"C:\Projects\pentana\era_quote_result.json"


# ─────────────────────────────────────────────────────────────
#  SALES ORDER
# ─────────────────────────────────────────────────────────────

def create_sales_order(window, make_code, customer_id, parts, counterman=None):
    """
    Creates a sales order in screen 2525.

    Args:
        window:      ERA Port window
        make_code:   e.g. "TO"
        customer_id: customer number string e.g. "158746"
        parts:       list of dicts [{ "part_number": "2321721010", "qty": 1 }]
        counterman:  optional e.g. "JOEL" — asked after two Enters post-customer
                     if None just presses Enter to keep default

    Returns:
        dict saved to OUTPUT_FILE JSON

    Exact sequence:
        2525 → make code → Enter (invoice#) → customer
        → Enter → Enter → counterman → Enter (order type) → parts
    """
    log.info(f"=== SALES ORDER | make={make_code} customer={customer_id} parts={len(parts)} ===")

    # Navigate to 2525
    navigate_to(window, "2525")
    time.sleep(WAIT_LONG)

    # Make code
    _send(window, make_code)

    # Enter on Invoice# (blank — not a quote)
    _enter(window)

    # Customer ID
    _send(window, customer_id)

    # Enter (first skip after customer)
    _enter(window)

    # Enter (second skip)
    _enter(window)

    # Counterman — asked here after the two enters
    if counterman:
        log.info(f"Setting counterman: {counterman}")
        _send(window, counterman)
    else:
        _enter(window)

    # Order type — always just Enter (not changing in prod)
    _enter(window)

    # Enter all parts
    for part in parts:
        _enter_part(window, part)

    # Empty Enter — signals end of parts
    _enter(window)

    # E + Enter (first)
    _send(window, "E")

    # E + Enter (second)
    _send(window, "E")

    # Read summary screen and save to JSON before pressing S
    time.sleep(WAIT_LONG)
    screen = read_screen_text(window)
    result = _parse_summary(screen, mode="sales", make_code=make_code,
                            customer_id=customer_id, parts=parts)
    _save_json(result)

    # S to save
    log.info("Saving sales order (S)...")
    window.set_focus()
    send_keys("S")
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    log.info(f"✅ Sales order done. Invoice#: {result.get('invoice_number')}")
    return result


# ─────────────────────────────────────────────────────────────
#  QUOTE
# ─────────────────────────────────────────────────────────────

def create_quote(window, make_code, customer_id, parts, counterman=None):
    """
    Creates a quote in screen 2525.
    Identical to sales order except PQ is typed after the make code.

    Args:
        window:      ERA Port window
        make_code:   e.g. "TO"
        customer_id: customer number string e.g. "158746"
        parts:       list of dicts [{ "part_number": "2321721010", "qty": 1 }]
        counterman:  optional e.g. "JOEL" — if None just presses Enter

    Returns:
        dict saved to OUTPUT_FILE JSON
    """
    log.info(f"=== QUOTE | make={make_code} customer={customer_id} parts={len(parts)} ===")

    # Navigate to 2525
    navigate_to(window, "2525")
    time.sleep(WAIT_LONG)

    # Make code
    _send(window, make_code)

    # PQ — this is the only difference from sales order
    # Switches screen from "Counter Sales" to "QUOTES"
    _send(window, "PQ")

    # Enter on Quote# (system assigns number on save)
    _enter(window)

    # Customer ID
    _send(window, customer_id)

    # Enter (skip field after customer)
    _enter(window)

    # Counterman — type if provided, otherwise just Enter
    if counterman:
        log.info(f"Setting counterman: {counterman}")
        _send(window, counterman)
    else:
        _enter(window)

    # Order type — always just Enter
    _enter(window)

    # Enter all parts
    for part in parts:
        _enter_part(window, part)

    # Empty Enter — signals end of parts
    _enter(window)

    # E + Enter (first)
    _send(window, "E")

    # E + Enter (second)
    _send(window, "E")

    # Read summary screen and save to JSON before pressing S
    time.sleep(WAIT_LONG)
    screen = read_screen_text(window)
    result = _parse_summary(screen, mode="quote", make_code=make_code,
                            customer_id=customer_id, parts=parts)
    _save_json(result)

    # S to save
    log.info("Saving quote (S)...")
    window.set_focus()
    send_keys("S")
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    log.info(f"✅ Quote done. Quote#: {result.get('quote_number')}")
    return result


# ─────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _send(window, text, wait=WAIT_MEDIUM):
    """Types text and presses Enter."""
    window.set_focus()
    send_keys(str(text), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(wait)


def _enter(window, wait=WAIT_SHORT):
    """Just presses Enter — used to skip optional fields."""
    window.set_focus()
    send_keys("{ENTER}")
    time.sleep(wait)


def _enter_part(window, part):
    """
    Enters one part line: part number + Enter, qty + Enter.

    part = { "part_number": "2321721010", "qty": 1 }
    """
    pn  = str(part["part_number"])
    qty = str(part.get("qty", 1))
    log.info(f"  Part: {pn}  Qty: {qty}")
    _send(window, pn)
    _send(window, qty)


def _parse_summary(screen_text, mode, make_code, customer_id, parts):
    """
    Parses the summary screen (shown after E+E) to build the result dict.

    Summary screen fields captured (from screenshots img_3, img_11, img_13):
      Invoice# / Quote#, Customer#, Sale Type, Pay-Method,
      Order Date, Required Date, Ship To,
      Total (No Tax), GST, Misc, Freight, Total Invoice/Quote,
      Total Line Items, Order Type
    """
    result = {
        "mode":          mode,          # "sales" or "quote"
        "make_code":     make_code,
        "customer_id":   customer_id,
        "parts":         parts,
    }

    # Invoice# or Quote# — alphanumeric e.g. "1980376D", "1104172D"
    inv_m = re.search(r"Invoice#?\s+([A-Z0-9]+)", screen_text, re.IGNORECASE)
    qt_m  = re.search(r"Quote#?\s+([A-Z0-9]+)",   screen_text, re.IGNORECASE)

    if mode == "sales" and inv_m:
        result["invoice_number"] = inv_m.group(1).strip()
    elif mode == "quote" and qt_m:
        result["quote_number"] = qt_m.group(1).strip()

    # Control No (sales order only)
    ctrl = re.search(r"Control\s+No\.?\s+([A-Z0-9]+)", screen_text, re.IGNORECASE)
    if ctrl:
        result["control_number"] = ctrl.group(1).strip()

    # Financials
    fin_patterns = {
        "total_no_tax":    r"Total\s*\(No\s*Tax\)\s+([\d.]+)",
        "gst":             r"GST\s+([\d.]+)",
        "misc":            r"Misc\s+([-\d.]+)",
        "freight":         r"Freight\s+([\d.]+)",
        "total_invoice":   r"Total\s+Invoice\s+([\d.]+)",
        "total_quote":     r"Total\s+Quote\s+([\d.]+)",
        "total_line_items":r"Total\s+Line\s+It[a-z]+\s+([\d.]+)",
        "order_type":      r"Order\s+Type\s+([A-Z]+)",
        "pay_method":      r"Pay-Method\s+([A-Z]+)",
        "sale_type":       r"Sale\s+Type\s+([A-Z]+)",
        "order_date":      r"Order\s+Date\s+([\d/]+)",
    }

    for key, pattern in fin_patterns.items():
        m = re.search(pattern, screen_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # Convert numeric strings to float
            try:
                result[key] = float(val)
            except ValueError:
                result[key] = val

    return result


def _save_json(data):
    """Saves result dict to OUTPUT_FILE."""
    try:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        log.info(f"💾 Saved to: {OUTPUT_FILE}")
    except Exception as e:
        log.error(f"Could not save JSON: {e}")


# ─────────────────────────────────────────────────────────────
#  STANDALONE TEST
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    TEST_MAKE      = "TO"
    TEST_CUSTOMER  = "158746"
    TEST_COUNTERMAN = "JOEL"
    TEST_PARTS = [
        {"part_number": "2321721010", "qty": 1},
        {"part_number": "2330030410", "qty": 2},
    ]

    try:
        window = launch_era_port()
        login(window)

        # ── Test sales order ──
        result = create_sales_order(
            window,
            make_code=TEST_MAKE,
            customer_id=TEST_CUSTOMER,
            parts=TEST_PARTS,
        )
        print("\n✅ Sales order result:")
        print(json.dumps(result, indent=2))

        # ── Test quote ──
        # result = create_quote(
        #     window,
        #     make_code=TEST_MAKE,
        #     customer_id=TEST_CUSTOMER,
        #     parts=TEST_PARTS,
        #     counterman=TEST_COUNTERMAN,
        # )
        # print("\n✅ Quote result:")
        # print(json.dumps(result, indent=2))

        window = logoff_era(window)

    except Exception as e:
        log.error(f"Error: {e}")
        raise