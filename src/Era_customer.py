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

MENU_CUSTOMER = "2120"
MENU_INVOICE  = "2525"

OUTPUT_FILE = r"C:\Projects\pentana\era_customer_result.json"


# ═══════════════════════════════════════════════════════════════
#  CUSTOMER LOOKUP  (Screen 2120)
# ═══════════════════════════════════════════════════════════════

def lookup_customer(window, search_term):
    log.info(f"Looking up customer: '{search_term}'")

    navigate_to(window, MENU_CUSTOMER)
    time.sleep(WAIT_LONG)

    window.set_focus()
    send_keys(search_term.replace(" ", "{SPACE}"), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    # TEMP DEBUG — shows exactly what ERA copied from screen
    print("=== RAW SCREEN (lookup) ===")
    print(screen[:1500])
    print("===========================")

    # If search results list is showing, do NOT treat as direct match
    if "Search Results" in screen:
        log.info("Search results list detected.")
        results = _parse_customer_search_results(screen)
        if not results:
            log.warning(f"No customers found for: '{search_term}'")
            return None
        log.info(f"Found {len(results)} customer(s).")
        return results

    # Direct match — landed straight on detail screen
    if _is_customer_detail_screen(screen):
        log.info("Direct match — on customer detail screen.")
        return [_parse_customer_detail(screen)]

    log.warning(f"No customers found for: '{search_term}'")
    return None


def select_customer(window, search_term, line_number):
    """
    Re-searches and picks a specific line number.
    Called once per entry in a fresh ERA session.
    """
    log.info(f"Selecting line {line_number} for search: '{search_term}'")

    navigate_to(window, MENU_CUSTOMER)
    time.sleep(WAIT_LONG)

    window.set_focus()
    send_keys(search_term.replace(" ", "{SPACE}"), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    # Pick the line
    send_keys(str(line_number), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)

    # TEMP DEBUG
    print(f"=== RAW SCREEN (line {line_number}) ===")
    print(screen[:1500])
    print("========================================")

    return _parse_customer_detail(screen)


def get_customer_credit_limit(window, customer_number):
    log.info(f"Getting credit limit for customer: {customer_number}")

    navigate_to(window, MENU_INVOICE)
    time.sleep(WAIT_LONG)

    window.set_focus()
    send_keys("{ENTER}")
    time.sleep(WAIT_SHORT)
    send_keys(customer_number, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    screen = read_screen_text(window)
    return _parse_credit_limit(screen)


# ═══════════════════════════════════════════════════════════════
#  PARSERS
# ═══════════════════════════════════════════════════════════════

def _is_customer_detail_screen(screen_text):
    """Returns True only if we are on the full customer detail page."""
    if "Search Results" in screen_text:
        return False
    indicators = ["Entity ID", "First Name", "Last Name", "Street Add1", "Suburb", "Postal Code"]
    hits = sum(1 for kw in indicators if kw in screen_text)
    return hits >= 4

def _parse_customer_search_results(screen_text):
    results = []
    lines = screen_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    for line in lines:
        # Format: |   1   381502 Joel Hughes      Test Test 3131                        S        |
        match = re.match(r"^\|\s+(\d+)\s+(\d{6})\s+(.+?)\s{2,}(.*?)\s{2,}(\S+)\s*\|$", line)
        if match:
            results.append({
                "line":            int(match.group(1)),
                "customer_number": match.group(2).strip(),
                "name":            match.group(3).strip(),
                "address":         match.group(4).strip(),
                "phone":           "",
                "type":            match.group(5).strip(),
            })

    return results

def _parse_customer_detail(screen_text):
    """
    Parses the customer detail screen (Entity Master).

    Fields visible on screen:
        Entity ID, Business, First Name, Middle Name, Last Name,
        Street Add1, Street Add2, Suburb, Postal Code, State, Country,
        Entity Type, Customer Type, Preferred, Sort Name,
        Contact Type, Salutation, Title, Attention, Privacy Cde
    """
    result = {
        "entity_id":     None,
        "business":      None,
        "first_name":    None,
        "middle_name":   None,
        "last_name":     None,
        "name":          None,
        "street_add1":   None,
        "street_add2":   None,
        "suburb":        None,
        "postal_code":   None,
        "state":         None,
        "country":       None,
        "entity_type":   None,
        "customer_type": None,
        "contact_type":  None,
        "preferred":     None,
        "sort_name":     None,
    }

    m = re.search(r"Entity\s*ID\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["entity_id"] = m.group(1).strip()

    m = re.search(r"(?:1\.\s*)?Business\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["business"] = m.group(1).strip()

    m = re.search(r"(?:2\.\s*)?First\s*N(?:ame)?\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["first_name"] = m.group(1).strip()

    m = re.search(r"(?:3\.\s*)?Middle\s*N(?:ame)?\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["middle_name"] = m.group(1).strip()

    m = re.search(r"(?:4\.\s*)?Last\s*N(?:ame)?\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["last_name"] = m.group(1).strip()

    if result["first_name"] and result["last_name"]:
        result["name"] = f"{result['first_name']} {result['last_name']}"
    elif result["business"]:
        result["name"] = result["business"]

    m = re.search(r"(?:7\.\s*)?Street\s*Add1\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["street_add1"] = m.group(1).strip()

    m = re.search(r"(?:8\.\s*)?Street\s*Add2\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["street_add2"] = m.group(1).strip()

    m = re.search(r"(?:9\.\s*)?Suburb\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["suburb"] = m.group(1).strip()

    m = re.search(r"(?:10\.\s*)?Postal\s*Code\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["postal_code"] = m.group(1).strip()

    m = re.search(r"(?:11\.\s*)?State\s*[:\|]\s*(\S+)", screen_text, re.IGNORECASE)
    if m: result["state"] = m.group(1).strip()

    m = re.search(r"(?:12\.\s*)?Country\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["country"] = m.group(1).strip()

    m = re.search(r"Entity\s*Type\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["entity_type"] = m.group(1).strip()

    m = re.search(r"Cust(?:omer)?\s*Type\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["customer_type"] = m.group(1).strip()

    m = re.search(r"(?:19\.\s*)?Contact\s*Type\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["contact_type"] = m.group(1).strip()

    m = re.search(r"(?:5\.\s*)?Preferred\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["preferred"] = m.group(1).strip()

    m = re.search(r"(?:6\.\s*)?Sort\s*N(?:ame)?\s*[:\|]\s*(.+?)(?:\s*\||\n|$)", screen_text, re.IGNORECASE)
    if m: result["sort_name"] = m.group(1).strip()

    return result


def _parse_credit_limit(screen_text):
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

    TEST_SEARCH = "Joel Hughe"

    try:
        era_window = launch_era_port()
        login(era_window)

        # First pass — just to count how many entries exist
        results = lookup_customer(era_window, TEST_SEARCH)

        if not results:
            print("❌ No customers found.")
            era_window = logoff_era(era_window)

        elif len(results) == 1 and results[0].get("entity_id"):
            # Direct detail hit — already parsed
            customer = results[0]
            print("\n✅ Single customer found (direct):")
            print(f"   Entity ID:    {customer.get('entity_id')}")
            print(f"   Name:         {customer.get('name')}")
            print(f"   Street:       {customer.get('street_add1')}")
            print(f"   Suburb:       {customer.get('suburb')}")
            print(f"   State:        {customer.get('state')}")
            print(f"   Postal Code:  {customer.get('postal_code')}")
            print(f"   Entity Type:  {customer.get('entity_type')}")
            print(f"   Customer Type:{customer.get('customer_type')}")

            with open(OUTPUT_FILE, "w") as f:
                json.dump(customer, f, indent=2)
            print(f"\n💾 Saved to: {OUTPUT_FILE}")

            era_window = logoff_era(era_window)

        else:
            # Multiple entries — loop through each one
            # results list gives us the count (e.g. 3)
            total_lines = len(results)
            print(f"\n✅ Found {total_lines} entries:")
            for r in results:
                print(f"   [{r['line']}] {r['customer_number']} — {r['name']} — {r['address']}")

            all_customers = []

            for i in range(1, total_lines + 1):
                print(f"\n--- Fetching entry {i} of {total_lines} ---")

                # Close and reopen ERA fresh for each entry
                era_window = logoff_era(era_window)
                login(era_window)

                customer = select_customer(era_window, TEST_SEARCH, i)
                all_customers.append(customer)
                print(f"   ✅ {customer.get('name')} — {customer.get('street_add1')}, {customer.get('suburb')}")

            with open(OUTPUT_FILE, "w") as f:
                json.dump(all_customers, f, indent=2)
            print(f"\n💾 All {total_lines} customers saved to: {OUTPUT_FILE}")

            era_window = logoff_era(era_window)

    except Exception as e:
        log.error(f"Error: {e}")
        raise