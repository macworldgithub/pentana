"""
ERA Power — Quote & Sales Order Module
=======================================
Screen 2525: Create quotes and convert winning quotes to invoices.

Key flows:
  - create_quote()       → new quote (PQ mode), save/print
  - requote()            → modify existing quote with lower price
  - convert_to_invoice() → turn a won quote into a sales order / invoice

Usage (standalone test):
    py -3.14 era_quote.py

Usage (from orchestrator):
    from era_quote import create_quote, requote, convert_to_invoice
"""

import re
import time
import json
import logging
from pywinauto.keyboard import send_keys

try:
    from Era_power import (
        find_era_window, launch_era_port, login, logoff_era,
        read_screen_text, type_and_enter, navigate_to,
        WAIT_SHORT, WAIT_MEDIUM, WAIT_LONG,
    )
except ImportError:
    raise ImportError(
        "era_power.py must be in the same directory as era_quote.py"
    )

log = logging.getLogger("eraPower.quote")

MENU_QUOTE    = "2525"
OUTPUT_FILE   = r"C:\Projects\pentana\era_quote_result.json"


# ═══════════════════════════════════════════════════════════════
#  CREATE QUOTE  (Screen 2525 → PQ mode)
# ═══════════════════════════════════════════════════════════════

def create_quote(window, make_code, customer_search, parts, counterman=None, order_type=None):
    """
    Creates a new quote in screen 2525 using the PQ sequence.

    Args:
        window:          ERA Port window
        make_code:       e.g. "TO", "GM"
        customer_search: customer number or partial name string
        parts:           list of dicts:
                         [{ "part_number": "2321721010", "qty": 1, "sale_price": 23.75 }]
        counterman:      optional counterman number (leave None to keep default)
        order_type:      optional order type (leave None to keep "Daily order" default)

    Returns:
        dict: { quote_number, make_code, customer, parts, status }

    Screen flow per docs:
        2525 → make code → PQ + Enter → screen says "quote" → Enter
        → customer number or partial name → counterman (if needed)
        → order type (if needed) → Enter on ID#
        → for each part: part_number → Enter → qty → Enter
        → Enter (finish parts)
        → E + Enter → E + Enter
        → P + Enter (print/email) or S + Enter (save only)
    """
    log.info(f"Creating quote — make: {make_code}, customer: {customer_search}")
    log.info(f"Parts to quote: {len(parts)} line(s)")

    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Step 1: Enter make code
    log.info(f"Entering make code: {make_code}")
    window.set_focus()
    send_keys(make_code, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 2: Enter PQ to switch from invoice to quote mode
    log.info("Switching to quote mode (PQ)...")
    window.set_focus()
    send_keys("PQ", pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Screen now shows "QUOTE" instead of "INVOICE"
    # Step 3: Press Enter to pass the invoice# / quote# field
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 4: Enter customer number or partial name
    log.info(f"Entering customer: {customer_search}")
    window.set_focus()
    send_keys(str(customer_search), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 5: Counterman (optional — Enter to keep default)
    if counterman:
        log.info(f"Setting counterman: {counterman}")
        send_keys(str(counterman), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)

    # Step 6: Order type (optional — Enter to keep "Daily order")
    if order_type:
        log.info(f"Setting order type: {order_type}")
        send_keys(str(order_type), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)

    # Step 7: Press Enter on ID# field if prompted
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)

    # Step 8: Enter each part
    for part in parts:
        _enter_part_line(window, part)

    # Step 9: Press Enter on empty part# field to signal end of parts
    log.info("Finishing part entry...")
    window.set_focus()
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 10: E + Enter (first confirmation)
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 11: E + Enter (second confirmation)
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 12: Save the quote (S = save only, P = print/email)
    # Using S by default — orchestrator can override to P when needed
    log.info("Saving quote (S)...")
    send_keys("S")
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    # Read screen to get the assigned quote number
    screen = read_screen_text(window)

    log.debug("=== QUOTE CREATION RAW SCREEN ===")
    log.debug(repr(screen[:800]))

    quote_number = _parse_quote_number(screen)

    result = {
        "quote_number": quote_number,
        "make_code":    make_code,
        "customer":     customer_search,
        "parts":        parts,
        "status":       "saved",
    }

    log.info(f"✅ Quote created: #{quote_number}")
    return result


# ═══════════════════════════════════════════════════════════════
#  REQUOTE — Update price on existing quote
# ═══════════════════════════════════════════════════════════════

def requote(window, quote_number, updated_parts):
    """
    Modifies an existing quote with new (lower) prices.
    Called by the orchestrator when we need to undercut a competitor.

    Args:
        window:        ERA Port window
        quote_number:  str — existing quote number to modify
        updated_parts: list of dicts:
                       [{ "part_number": "2321721010", "qty": 1, "sale_price": 21.00 }]

    Returns:
        True if successful, False otherwise.

    Screen flow:
        2525 → make code → quote number → M (modify)
        → navigate to part line → update price
        → E + Enter → E + Enter → S/P

    # TODO: Confirm modify flow from live screen — specifically how to
    #       navigate to a specific part line to change its price.
    #       ERA Power may use line numbers or part number search.
    """
    log.info(f"Requoting quote #{quote_number} with {len(updated_parts)} updated part(s)...")

    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Enter make code
    # TODO: Store make_code in the state object so we can pass it here
    # For now the caller must ensure make code is entered via state
    window.set_focus()
    send_keys("{ENTER}")      # skip make code if already set, or handle via state
    time.sleep(WAIT_SHORT)

    # Enter the existing quote number to load it
    log.info(f"Loading quote: {quote_number}")
    send_keys(str(quote_number), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    # Read screen to confirm we loaded the right quote
    screen = read_screen_text(window)
    if quote_number not in screen:
        log.warning(f"Could not confirm quote #{quote_number} loaded.")

    # Press M to modify
    log.info("Entering modify mode (M)...")
    send_keys("M")
    time.sleep(WAIT_MEDIUM)

    # Update price for each part
    for part in updated_parts:
        _modify_part_price(window, part)

    # Finalise
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    send_keys("S")
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    log.info(f"✅ Quote #{quote_number} updated with new prices.")
    return True


# ═══════════════════════════════════════════════════════════════
#  CONVERT QUOTE TO INVOICE (Sales Order)
# ═══════════════════════════════════════════════════════════════

def convert_to_invoice(window, make_code, customer_search, parts, counterman=None, order_type=None):
    """
    Creates a sales order / invoice in screen 2525.
    Called ONLY after winning the PartsCheck competition.

    This is the same as create_quote() but WITHOUT the PQ step,
    and ends with B (both — complete invoice and email/print).

    Args:
        window:          ERA Port window
        make_code:       e.g. "TO"
        customer_search: customer number or partial name
        parts:           list of dicts with final agreed prices
        counterman:      optional
        order_type:      optional

    Returns:
        dict: { invoice_number, make_code, customer, parts, status }

    Screen flow per docs:
        2525 → make code → Enter on invoice#
        → customer → counterman → order type → Enter on ID#
        → parts + qty loop
        → E + Enter → E + Enter → B (both = complete + email/print)
    """
    log.info(f"Creating invoice — make: {make_code}, customer: {customer_search}")
    log.info(f"Parts on invoice: {len(parts)} line(s)")

    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Step 1: Enter make code
    window.set_focus()
    send_keys(make_code, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 2: Press Enter on invoice# (no PQ — this is a real invoice)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 3: Customer
    log.info(f"Entering customer: {customer_search}")
    send_keys(str(customer_search), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 4: Counterman
    if counterman:
        send_keys(str(counterman), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)

    # Step 5: Order type
    if order_type:
        send_keys(str(order_type), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)

    # Step 6: ID# prompt
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)

    # Step 7: Enter each part
    for part in parts:
        _enter_part_line(window, part)

    # Step 8: Empty Enter to end part entry
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 9: E + Enter (first)
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 10: E + Enter (second)
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 11: B = Both (complete invoice AND email/print)
    log.info("Finalising invoice (B = both)...")
    send_keys("B")
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    log.debug("=== INVOICE CREATION RAW SCREEN ===")
    log.debug(repr(screen[:800]))

    invoice_number = _parse_invoice_number(screen)

    result = {
        "invoice_number": invoice_number,
        "make_code":      make_code,
        "customer":       customer_search,
        "parts":          parts,
        "status":         "invoiced",
    }

    log.info(f"✅ Invoice created: #{invoice_number}")
    return result


# ═══════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

def _enter_part_line(window, part):
    """
    Enters a single part line (part number + qty) into 2525.

    part = { "part_number": "2321721010", "qty": 1, "sale_price": 23.75 }

    Screen flow:
        Input part number → Enter
        Input qty → Enter
        (repeat for next part)

    # NOTE: sale_price is NOT entered here — ERA Power pulls it automatically.
    #       Price override (if needed for requote) uses _modify_part_price().
    #       Confirm with client whether direct price entry is supported on new lines.
    """
    log.info(f"  Entering part: {part['part_number']} × {part.get('qty', 1)}")

    window.set_focus()
    send_keys(str(part["part_number"]), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    send_keys(str(part.get("qty", 1)), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)


def _modify_part_price(window, part):
    """
    Updates the price for a specific part on an existing quote.

    # TODO: Confirm the exact key sequence for modifying a line price.
    #       ERA Power may require:
    #         - Typing the line number then navigating to price field, OR
    #         - Searching by part number then tabbing to price field
    #       Update this function after first live test.
    """
    log.info(f"  Updating price: {part['part_number']} → ${part['sale_price']}")

    window.set_focus()

    # Placeholder sequence — update after confirming live screen behaviour
    # Common pattern: type line number → Tab to price field → type new price → Enter
    send_keys(str(part.get("line_number", "")), pause=0.05)
    send_keys("{TAB}")
    time.sleep(WAIT_SHORT)

    send_keys(str(part["sale_price"]), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)


def _parse_quote_number(screen_text):
    """
    Extracts assigned quote number from the screen after saving.

    # TODO: Confirm exact label used in ERA Power for quote number.
    #       May be "Quote#", "Q#", "Ref#" etc.
    """
    patterns = [
        r"Quote#?\s*[:\s]*(\d+)",
        r"Q#?\s*[:\s]*(\d+)",
        r"Ref#?\s*[:\s]*(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, screen_text, re.IGNORECASE)
        if m:
            return m.group(1)
    log.warning("Could not parse quote number from screen.")
    return None


def _parse_invoice_number(screen_text):
    """
    Extracts invoice number from the screen after completing.

    # TODO: Confirm exact label used in ERA Power for invoice number.
    """
    patterns = [
        r"Invoice#?\s*[:\s]*(\d+)",
        r"Inv#?\s*[:\s]*(\d+)",
        r"#\s*(\d{5,})",
    ]
    for pattern in patterns:
        m = re.search(pattern, screen_text, re.IGNORECASE)
        if m:
            return m.group(1)
    log.warning("Could not parse invoice number from screen.")
    return None


# ═══════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # ── hardcoded test values — replace with dynamic data in production ──
    TEST_MAKE     = "TO"
    TEST_CUSTOMER = "ABC"
    TEST_PARTS    = [
        { "part_number": "2321721010", "qty": 1, "sale_price": 23.75 },
    ]

    try:
        era_window = launch_era_port()
        login(era_window)

        # Test: create a quote
        result = create_quote(
            era_window,
            make_code=TEST_MAKE,
            customer_search=TEST_CUSTOMER,
            parts=TEST_PARTS,
        )

        print("\n✅ Quote created!")
        print(f"   Quote#:   {result['quote_number']}")
        print(f"   Customer: {result['customer']}")
        print(f"   Parts:    {len(result['parts'])}")
        print(f"   Status:   {result['status']}")

        with open(OUTPUT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Saved to: {OUTPUT_FILE}")

        era_window = logoff_era(era_window)

    except Exception as e:
        log.error(f"Error: {e}")
        raise