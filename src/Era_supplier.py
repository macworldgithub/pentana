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
        → if multiple: list appears → type line number → Enterap15
        → vendor detail screen shows
    """
    log.info(f"Looking up supplier: '{search_term}'")

    navigate_to(window, MENU_SUPPLIER)
    time.sleep(WAIT_LONG)

    window.set_focus()
    send_keys(search_term, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)      # wait for first enter to register
    send_keys("{ENTER}")         # second enter
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)
    print("=== RAW SCREEN ===")
    print(screen)
    print("==================")

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


# def _parse_supplier_detail(screen_text):
#     result = {
#         "vendor_number":   None,
#         "name":            None,
#         "sort_name":       None,
#         "address":         None,
#         "suburb":          None,
#         "state":           None,
#         "postcode":        None,
#         "tel":             None,
#         "email":           None,
#         "fax":             None,
#         "mobile":          None,
#         "contact":         None,
#         "payment_terms":   None,
#         "comments":        None,
#         "ytd_purchases":   None,
#         "pyr_purchases":   None,
#         "gst_reg_no":      None,
#         "eft_active":      None,
#         "remittance":      None,
#     }

#     m = re.search(r"Vendor\s*No\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["vendor_number"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Name\s*[:\|]\s*(.+?)(?:\s{2,}User|\|)", screen_text, re.IGNORECASE)
#     if m: result["name"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Sort\s*Name\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
#     if m: result["sort_name"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Address\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
#     if m: result["address"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Suburb\s*[:\|]\s*(.+?)(?:\s{2,}|\|)", screen_text, re.IGNORECASE)
#     if m: result["suburb"] = m.group(1).strip()

#     m = re.search(r"\d+\s+State\s*[:\|]\s*(.+?)(?:\s{2,}|\|)", screen_text, re.IGNORECASE)
#     if m: result["state"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Postcode\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["postcode"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Tel\.\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
#     if m: result["tel"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Email\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["email"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Fax\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["fax"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Mobile\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["mobile"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Contact\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
#     if m: result["contact"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Terms\s*[:\|]\s*(.+?)(?:YTD|\|)", screen_text, re.IGNORECASE)
#     if m: result["payment_terms"] = m.group(1).strip()

#     m = re.search(r"YTD\s*Purchases\s*[:\|]\s*([\d,\.]+)", screen_text, re.IGNORECASE)
#     if m: result["ytd_purchases"] = m.group(1).strip()

#     m = re.search(r"PYR\s*Purchases\s*[:\|]\s*([\d,\.]+)", screen_text, re.IGNORECASE)
#     if m: result["pyr_purchases"] = m.group(1).strip()

#     m = re.search(r"\d+\s+Comments\s*[:\|]\s*(.+?)(?:\s{2,}|\|)", screen_text, re.IGNORECASE)
#     if m: result["comments"] = m.group(1).strip()

#     m = re.search(r"GST\s*Registration\s*No\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["gst_reg_no"] = m.group(1).strip()

#     m = re.search(r"EFT\s*Active.*?[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["eft_active"] = m.group(1).strip()

#     m = re.search(r"Remittance\s*Advice.*?[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
#     if m: result["remittance"] = m.group(1).strip()

#     return result

def _parse_supplier_detail(screen_text):
    result = {
        "vendor_number":        None,
        "inactive":             None,
        "name":                 None,
        "user":                 None,
        "sort_name":            None,
        "address":              None,
        "suburb":               None,
        "state":                None,
        "postcode":             None,
        "tel":                  None,
        "email":                None,
        "fax":                  None,
        "mobile":               None,
        "contact":              None,
        "payment_terms":        None,
        "comments":             None,
        "ytd_purchases":        None,
        "pyr_purchases":        None,
        "default_discount_pct": None,
        "gst_charged_on_inv":   None,
        "gst_reg_no":           None,
        "eft_active":           None,
        "withholding_tax":      None,
        "remittance":           None,
        "payment_group":        None,
        "supplier_group":       None,
    }

    def clean(val):
        """Strip pipes, underscores, whitespace — return None if empty."""
        if not val:
            return None
        val = val.strip().strip("|").strip()
        if not val or all(c in "_ " for c in val):
            return None
        return val

    m = re.search(r"Vendor\s*No\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["vendor_number"] = clean(m.group(1))

    m = re.search(r"Inactive\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["inactive"] = clean(m.group(1))

    m = re.search(r"\d+\s+Name\s*[:\|]\s*(.+?)(?:\s{2,}User|\|)", screen_text, re.IGNORECASE)
    if m: result["name"] = clean(m.group(1))

    m = re.search(r"User\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["user"] = clean(m.group(1))

    m = re.search(r"\d+\s+Sort\s*Name\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
    if m: result["sort_name"] = clean(m.group(1))

    m = re.search(r"\d+\s+Address\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
    if m: result["address"] = clean(m.group(1))

    m = re.search(r"\d+\s+Suburb\s*[:\|]\s*(.+?)(?:\s{2,}|\|)", screen_text, re.IGNORECASE)
    if m: result["suburb"] = clean(m.group(1))

    m = re.search(r"\d+\s+State\s*[:\|]\s*(.+?)(?:\s{2,}|\|)", screen_text, re.IGNORECASE)
    if m: result["state"] = clean(m.group(1))

    m = re.search(r"\d+\s+Postcode\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["postcode"] = clean(m.group(1))

    m = re.search(r"\d+\s+Tel\.\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
    if m: result["tel"] = clean(m.group(1))

    m = re.search(r"\d+\s+Email\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["email"] = clean(m.group(1))

    m = re.search(r"\d+\s+Fax\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["fax"] = clean(m.group(1))

    m = re.search(r"\d+\s+Mobile\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
    if m: result["mobile"] = clean(m.group(1))

    m = re.search(r"\d+\s+Contact\s*[:\|]\s*(.+?)(?:\s*\||\n)", screen_text, re.IGNORECASE)
    if m: result["contact"] = clean(m.group(1))

    m = re.search(r"\d+\s+Terms\s*[:\|]\s*(.+?)(?:YTD|\|)", screen_text, re.IGNORECASE)
    if m: result["payment_terms"] = clean(m.group(1))

    m = re.search(r"YTD\s*Purchases\s*[:\|]\s*([\d,\.]+)", screen_text, re.IGNORECASE)
    if m: result["ytd_purchases"] = clean(m.group(1))

    m = re.search(r"PYR\s*Purchases\s*[:\|]\s*([\d,\.]+)", screen_text, re.IGNORECASE)
    if m: result["pyr_purchases"] = clean(m.group(1))

    m = re.search(r"\d+\s+Comments\s*[:\|]\s*(.+?)(?:\s{2,}|\|)", screen_text, re.IGNORECASE)
    if m: result["comments"] = clean(m.group(1))

    m = re.search(r"Default\s*Discount\s*%\s*[:\|]\s*([\d\.]+)", screen_text, re.IGNORECASE)
    if m: result["default_discount_pct"] = clean(m.group(1))

    m = re.search(r"GST\s*Charged\s*on\s*Inv.*?[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["gst_charged_on_inv"] = clean(m.group(1))

    m = re.search(r"GST\s*Registration\s*No\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["gst_reg_no"] = clean(m.group(1))

    m = re.search(r"EFT\s*Active.*?[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["eft_active"] = clean(m.group(1))

    m = re.search(r"Withholding\s*Tax.*?[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["withholding_tax"] = clean(m.group(1))

    m = re.search(r"Remittance\s*Advice.*?[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["remittance"] = clean(m.group(1))

    m = re.search(r"\d+\s+Pay(?:ment)?\s*Group\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["payment_group"] = clean(m.group(1))

    m = re.search(r"\d+\s+Supplier\s*Group\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["supplier_group"] = clean(m.group(1))

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
    TEST_SEARCH = "14338"

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