"""
ERA Power — Supplier / Merchant Lookup Module
==============================================
Screen 2140: Look up vendor/supplier info by name or number.

Usage (standalone test):
    py -3.14 era_supplier.py

Usage (from orchestrator):
    from era_supplier import lookup_supplier
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
        "era_power.py must be in the same directory as era_supplier.py"
    )

log = logging.getLogger("eraPower.supplier")

MENU_SUPPLIER = "2140"
OUTPUT_FILE   = r"C:\Projects\pentana\era_supplier_result.json"


# ═══════════════════════════════════════════════════════════════
#  SUPPLIER LOOKUP  (Screen 2140)
# ═══════════════════════════════════════════════════════════════

def lookup_supplier(window, search_term):
    """
    Looks up a supplier/vendor in screen 2140.

    Args:
        window:      ERA Port window
        search_term: vendor number (e.g. "V0042") or partial name (e.g. "BOSCH")

    Returns:
        List of dicts if multiple matches, or single dict for exact match.
        Each dict: { line, vendor_number, name }
        Returns None if not found.

    Screen flow:
        2140 → type vendor number or partial name → Enter
        → if multiple: list appears → type line number → Enter
        → vendor detail screen shows
    """
    log.info(f"Looking up supplier: '{search_term}'")

    navigate_to(window, MENU_SUPPLIER)
    time.sleep(WAIT_LONG)

    window.set_focus()
    send_keys(search_term, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    log.debug("=== SUPPLIER SEARCH RAW SCREEN ===")
    log.debug(repr(screen[:1000]))

    # Direct hit — landed on vendor detail page
    if _is_supplier_detail_screen(screen):
        log.info("Direct match — on supplier detail screen.")
        return [_parse_supplier_detail(screen)]

    # Multiple results list
    results = _parse_supplier_search_results(screen)

    if not results:
        log.warning(f"No suppliers found for: '{search_term}'")
        return None

    log.info(f"Found {len(results)} supplier(s).")
    return results


def select_supplier(window, line_number):
    """
    After lookup_supplier() returns a list, call this to pick one.

    Args:
        window:      ERA Port window
        line_number: int or str

    Returns:
        dict: full supplier detail
    """
    log.info(f"Selecting supplier line: {line_number}")

    window.set_focus()
    send_keys(str(line_number), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    log.debug("=== SUPPLIER DETAIL RAW SCREEN ===")
    log.debug(repr(screen[:1000]))

    return _parse_supplier_detail(screen)


# ═══════════════════════════════════════════════════════════════
#  PARSERS
# ═══════════════════════════════════════════════════════════════

def _is_supplier_detail_screen(screen_text):
    """Returns True if we're on a vendor detail screen."""
    indicators = ["Vendor", "Phone", "Address", "Contact", "ABN", "Terms"]
    hits = sum(1 for kw in indicators if kw in screen_text)
    return hits >= 2


def _parse_supplier_search_results(screen_text):
    """
    Parses the supplier search results list.

    Typical line format:
        1   V0042   BOSCH AUSTRALIA
        2   V0043   BOSCH INDUSTRIAL

    Returns list of dicts: [{ line, vendor_number, name }]

    # TODO: Confirm exact column layout from live screen.
    #       Vendor numbers may be numeric only — adjust regex if needed.
    """
    results = []
    lines = screen_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    for line in lines:
        # Match line_num  vendor_number  name
        match = re.match(r"^\s*(\d+)\s+([A-Z0-9\-]+)\s+(.+)$", line.strip())
        if match:
            results.append({
                "line":          int(match.group(1)),
                "vendor_number": match.group(2).strip(),
                "name":          match.group(3).strip(),
            })

    return results


def _parse_supplier_detail(screen_text):
    """
    Parses the vendor info screen.

    Extracts: vendor_number, name, phone, address, contact, abn, payment_terms

    # TODO: Confirm exact field labels from live screen — ERA Power may
    #       abbreviate labels differently (e.g. "Ph" vs "Phone", "Cont" vs "Contact").
    """
    result = {
        "vendor_number":  None,
        "name":           None,
        "phone":          None,
        "address":        None,
        "contact":        None,
        "abn":            None,
        "payment_terms":  None,
    }

    # Vendor number
    m = re.search(r"Vendor#?\s*[:\s]+([A-Z0-9\-]+)", screen_text, re.IGNORECASE)
    if m:
        result["vendor_number"] = m.group(1).strip()

    # Name
    m = re.search(r"Name\s*[:\s]+(.+)", screen_text, re.IGNORECASE)
    if m:
        result["name"] = m.group(1).strip()

    # Phone
    m = re.search(r"Ph(?:one)?\s*[:\s]+([\d\s\-\+\(\)]+)", screen_text, re.IGNORECASE)
    if m:
        result["phone"] = m.group(1).strip()

    # Address
    m = re.search(r"Addr(?:ess)?\s*[:\s]+(.+?)(?:\n|Phone|Ph|Contact|ABN|$)", screen_text, re.IGNORECASE | re.DOTALL)
    if m:
        result["address"] = m.group(1).strip()

    # Contact person
    m = re.search(r"Cont(?:act)?\s*[:\s]+(.+)", screen_text, re.IGNORECASE)
    if m:
        result["contact"] = m.group(1).strip()

    # ABN
    m = re.search(r"ABN\s*[:\s]+([\d\s]+)", screen_text, re.IGNORECASE)
    if m:
        result["abn"] = m.group(1).strip()

    # Payment terms
    m = re.search(r"Terms?\s*[:\s]+(.+)", screen_text, re.IGNORECASE)
    if m:
        result["payment_terms"] = m.group(1).strip()

    return result


# ═══════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # ── hardcoded test value — replace with dynamic data in production ──
    TEST_SEARCH = "BOSCH"

    try:
        era_window = launch_era_port()
        login(era_window)

        results = lookup_supplier(era_window, TEST_SEARCH)

        if not results:
            print("❌ No suppliers found.")
        elif len(results) == 1:
            supplier = results[0]
            print("\n✅ Supplier found (direct):")
        else:
            print(f"\n✅ Found {len(results)} suppliers:")
            for r in results:
                print(f"   [{r['line']}] {r['vendor_number']} — {r['name']}")

            print("\nSelecting line 1...")
            supplier = select_supplier(era_window, 1)

        if results:
            print(f"\n   Vendor#:       {supplier.get('vendor_number')}")
            print(f"   Name:          {supplier.get('name')}")
            print(f"   Phone:         {supplier.get('phone')}")
            print(f"   Address:       {supplier.get('address')}")
            print(f"   Contact:       {supplier.get('contact')}")
            print(f"   ABN:           {supplier.get('abn')}")
            print(f"   Terms:         {supplier.get('payment_terms')}")

            with open(OUTPUT_FILE, "w") as f:
                json.dump(supplier, f, indent=2)
            print(f"\n💾 Saved to: {OUTPUT_FILE}")

        era_window = logoff_era(era_window)

    except Exception as e:
        log.error(f"Error: {e}")
        raise