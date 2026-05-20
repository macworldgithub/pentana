"""
ERA Power — Customer Account Module
====================================
Screen 2120: Look up customer info by name or number.
Screen 2525: Read credit limit during invoicing.

Follows the same patterns as the working Parts Inquiry module.
All navigation is blind-typed — we know the exact screen sequences.

Usage (standalone test):
    py -3.14 era_customer.py

Usage (from orchestrator):
    from era_customer import lookup_customer, get_customer_credit_limit
"""

import re
import time
import json
import logging
from pywinauto.keyboard import send_keys

# ── reuse shared helpers from the main era_power module ──────────────────────
# These are imported at runtime so this file can also run standalone
try:
    from Era_power import (
        find_era_window, launch_era_port, login, logoff_era,
        read_screen_text, type_and_enter, navigate_to,
        WAIT_SHORT, WAIT_MEDIUM, WAIT_LONG,
    )
except ImportError:
    raise ImportError(
        "era_power.py must be in the same directory as era_customer.py"
    )

log = logging.getLogger("eraPower.customer")

# Screen codes
MENU_CUSTOMER = "2120"
MENU_INVOICE  = "2525"

OUTPUT_FILE = r"C:\Projects\pentana\era_customer_result.json"


# ═══════════════════════════════════════════════════════════════
#  CUSTOMER LOOKUP  (Screen 2120)
# ═══════════════════════════════════════════════════════════════

def lookup_customer(window, search_term):
    """
    Looks up a customer in screen 2120.

    Args:
        window:      ERA Port window
        search_term: partial name (e.g. "ABC") or customer number (e.g. "10042")

    Returns:
        List of dicts if multiple results, or single dict if exact match.
        Each dict: { line, customer_number, name }
        Returns None if nothing found.

    Screen flow:
        2120 → input partial name or number → Enter
        → search results list appears
        → type line number → Enter
        → basic customer info screen
    """
    log.info(f"Looking up customer: '{search_term}'")

    navigate_to(window, MENU_CUSTOMER)
    time.sleep(WAIT_LONG)

    # Type search term and press Enter
    window.set_focus()
    send_keys(search_term.replace(" ", "{SPACE}"), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    log.debug("=== CUSTOMER SEARCH RAW SCREEN ===")
    log.debug(repr(screen[:1000]))

    # Check if we landed directly on a customer record (exact match)
    if _is_customer_detail_screen(screen):
        log.info("Direct match — on customer detail screen.")
        return [_parse_customer_detail(screen)]

    # Otherwise parse the search results list
    results = _parse_customer_search_results(screen)

    if not results:
        log.warning(f"No customers found for: '{search_term}'")
        return None

    log.info(f"Found {len(results)} customer(s).")
    return results


def select_customer(window, line_number):
    """
    After lookup_customer() returns a list, call this to pick one.
    Types the line number and returns the customer detail dict.

    Args:
        window:      ERA Port window
        line_number: int or str — the line number shown in search results

    Returns:
        dict: { customer_number, name, address, phone, credit_limit, balance }
    """
    log.info(f"Selecting customer line: {line_number}")

    window.set_focus()
    send_keys(str(line_number), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    log.debug("=== CUSTOMER DETAIL RAW SCREEN ===")
    log.debug(repr(screen[:1000]))

    return _parse_customer_detail(screen)


def get_customer_credit_limit(window, customer_number):
    """
    Reads the credit limit for a customer.
    Credit limits are visible in screen 2525 during invoicing.

    Args:
        window:          ERA Port window
        customer_number: str

    Returns:
        float credit limit or None
    """
    log.info(f"Getting credit limit for customer: {customer_number}")

    navigate_to(window, MENU_INVOICE)
    time.sleep(WAIT_LONG)

    # Enter customer number to load their invoice screen
    window.set_focus()
    send_keys("{ENTER}")           # skip invoice# field
    time.sleep(WAIT_SHORT)
    send_keys(customer_number, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    log.debug("=== CREDIT LIMIT RAW SCREEN ===")
    log.debug(repr(screen[:800]))

    return _parse_credit_limit(screen)


# ═══════════════════════════════════════════════════════════════
#  PARSERS
# ═══════════════════════════════════════════════════════════════

def _is_customer_detail_screen(screen_text):
    """Returns True if we're already on a customer detail page."""
    indicators = ["Cust#", "Phone", "Credit", "Balance", "Address"]
    hits = sum(1 for kw in indicators if kw in screen_text)
    return hits >= 2


def _parse_customer_search_results(screen_text):
    """
    Parses the search results list screen.

    Typical line format:
        1   10042   ABC MOTORS PTY LTD
        2   10089   ABCO ENGINEERING
        3   10120   ABCDEF PARTS

    Returns list of dicts: [{ line, customer_number, name }]

    # TODO: Confirm exact column positions once tested against live screen.
    #       Adjust regex if fields are fixed-width rather than space-delimited.
    """
    results = []
    lines = screen_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    for line in lines:
        # Match: line_num  customer_number  name
        match = re.match(r"^\s*(\d+)\s+(\d{4,7})\s+(.+)$", line.strip())
        if match:
            results.append({
                "line":            int(match.group(1)),
                "customer_number": match.group(2).strip(),
                "name":            match.group(3).strip(),
            })

    return results


def _parse_customer_detail(screen_text):
    """
    Parses the basic customer info screen.

    Extracts: customer_number, name, address, phone, credit_limit, balance

    # TODO: Confirm field labels once tested against live screen.
    #       ERA Power may use abbreviated labels — update patterns to match.
    """
    result = {
        "customer_number": None,
        "name":            None,
        "address":         None,
        "phone":           None,
        "credit_limit":    None,
        "balance":         None,
    }

    # Customer number
    m = re.search(r"Cust#?\s*[:\s]+(\d+)", screen_text, re.IGNORECASE)
    if m:
        result["customer_number"] = m.group(1).strip()

    # Name
    m = re.search(r"Name\s*[:\s]+(.+)", screen_text, re.IGNORECASE)
    if m:
        result["name"] = m.group(1).strip()

    # Phone
    m = re.search(r"Phone\s*[:\s]+([\d\s\-\+\(\)]+)", screen_text, re.IGNORECASE)
    if m:
        result["phone"] = m.group(1).strip()

    # Address — grab everything after "Address" or "Addr" up to next field
    m = re.search(r"Addr(?:ess)?\s*[:\s]+(.+?)(?:\n|Phone|Credit|$)", screen_text, re.IGNORECASE | re.DOTALL)
    if m:
        result["address"] = m.group(1).strip()

    # Credit limit
    m = re.search(r"Credit\s*(?:Limit)?\s*[:\s]+([\d,\.]+)", screen_text, re.IGNORECASE)
    if m:
        result["credit_limit"] = float(m.group(1).replace(",", ""))

    # Balance
    m = re.search(r"Balance\s*[:\s]+([\d,\.]+)", screen_text, re.IGNORECASE)
    if m:
        result["balance"] = float(m.group(1).replace(",", ""))

    return result


def _parse_credit_limit(screen_text):
    """
    Extracts credit limit value from screen 2525.
    # TODO: Confirm exact label used in 2525 for credit limit field.
    """
    m = re.search(r"Credit\s*(?:Limit)?\s*[:\s]+([\d,\.]+)", screen_text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", ""))
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
    TEST_SEARCH = "Joel Hughe"   # partial customer name to search

    try:
        era_window = launch_era_port()
        login(era_window)

        # Step 1: Search
        results = lookup_customer(era_window, TEST_SEARCH)

        if not results:
            print("❌ No customers found.")
        elif len(results) == 1:
            # Direct hit or single result
            customer = results[0]
            print("\n✅ Customer found (direct):")
        else:
            # Multiple results — print list and pick first for test
            print(f"\n✅ Found {len(results)} customers:")
            for r in results:
                print(f"   [{r['line']}] {r['customer_number']} — {r['name']}")

            # Step 2: Select line 1 for test
            print("\nSelecting line 1...")
            customer = select_customer(era_window, 1)

        if results:
            print(f"\n   Customer#:    {customer.get('customer_number')}")
            print(f"   Name:         {customer.get('name')}")
            print(f"   Phone:        {customer.get('phone')}")
            print(f"   Address:      {customer.get('address')}")
            print(f"   Credit Limit: ${customer.get('credit_limit')}")
            print(f"   Balance:      ${customer.get('balance')}")

            with open(OUTPUT_FILE, "w") as f:
                json.dump(customer, f, indent=2)
            print(f"\n💾 Saved to: {OUTPUT_FILE}")

        era_window = logoff_era(era_window)

    except Exception as e:
        log.error(f"Error: {e}")
        raise