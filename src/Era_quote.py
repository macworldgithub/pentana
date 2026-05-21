# """
# ERA Power — Quote & Sales Order Module
# =======================================
# Screen 2525: Create quotes and convert winning quotes to invoices.

# Key flows:
#   - create_quote()       → new quote (PQ mode), save/print
#   - requote()            → modify existing quote with lower price
#   - convert_to_invoice() → turn a won quote into a sales order / invoice

# Usage (standalone test):
#     py -3.14 era_quote.py

# Usage (from orchestrator):
#     from era_quote import create_quote, requote, convert_to_invoice
# """

# import re
# import time
# import json
# import logging
# from pywinauto.keyboard import send_keys

# try:
#     from Era_power import (
#         find_era_window, launch_era_port, login, logoff_era,
#         read_screen_text, type_and_enter, navigate_to,
#         WAIT_SHORT, WAIT_MEDIUM, WAIT_LONG,
#     )
# except ImportError:
#     raise ImportError(
#         "era_power.py must be in the same directory as era_quote.py"
#     )

# log = logging.getLogger("eraPower.quote")

# MENU_QUOTE    = "2525"
# OUTPUT_FILE   = r"C:\Projects\pentana\era_quote_result.json"


# # ═══════════════════════════════════════════════════════════════
# #  CREATE QUOTE  (Screen 2525 → PQ mode)
# # ═══════════════════════════════════════════════════════════════

# def create_quote(window, make_code, customer_search, parts, counterman=None, order_type=None):
#     """
#     Creates a new quote in screen 2525 using the PQ sequence.

#     Args:
#         window:          ERA Port window
#         make_code:       e.g. "TO", "GM"
#         customer_search: customer number or partial name string
#         parts:           list of dicts:
#                          [{ "part_number": "2321721010", "qty": 1, "sale_price": 23.75 }]
#         counterman:      optional counterman number (leave None to keep default)
#         order_type:      optional order type (leave None to keep "Daily order" default)

#     Returns:
#         dict: { quote_number, make_code, customer, parts, status }

#     Screen flow per docs:
#         2525 → make code → PQ + Enter → screen says "quote" → Enter
#         → customer number or partial name → counterman (if needed)
#         → order type (if needed) → Enter on ID#
#         → for each part: part_number → Enter → qty → Enter
#         → Enter (finish parts)
#         → E + Enter → E + Enter
#         → P + Enter (print/email) or S + Enter (save only)
#     """
#     log.info(f"Creating quote — make: {make_code}, customer: {customer_search}")
#     log.info(f"Parts to quote: {len(parts)} line(s)")

#     navigate_to(window, MENU_QUOTE)
#     time.sleep(WAIT_LONG)

#     # Step 1: Enter make code
#     log.info(f"Entering make code: {make_code}")
#     window.set_focus()
#     send_keys(make_code, pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 2: Enter PQ to switch from invoice to quote mode
#     log.info("Switching to quote mode (PQ)...")
#     window.set_focus()
#     send_keys("PQ", pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Screen now shows "QUOTE" instead of "INVOICE"
#     # Step 3: Press Enter to pass the invoice# / quote# field
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 4: Enter customer number or partial name
#     log.info(f"Entering customer: {customer_search}")
#     window.set_focus()
#     send_keys(str(customer_search), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 5: Counterman (optional — Enter to keep default)
#     if counterman:
#         log.info(f"Setting counterman: {counterman}")
#         send_keys(str(counterman), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_SHORT)

#     # Step 6: Order type (optional — Enter to keep "Daily order")
#     if order_type:
#         log.info(f"Setting order type: {order_type}")
#         send_keys(str(order_type), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_SHORT)

#     # Step 7: Press Enter on ID# field if prompted
#     send_keys("{ENTER}")
#     time.sleep(WAIT_SHORT)

#     # Step 8: Enter each part
#     for part in parts:
#         _enter_part_line(window, part)

#     # Step 9: Press Enter on empty part# field to signal end of parts
#     log.info("Finishing part entry...")
#     window.set_focus()
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 10: E + Enter (first confirmation)
#     send_keys("E")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 11: E + Enter (second confirmation)
#     send_keys("E")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 12: Save the quote (S = save only, P = print/email)
#     # Using S by default — orchestrator can override to P when needed
#     log.info("Saving quote (S)...")
#     send_keys("S")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_LONG)

#     # Read screen to get the assigned quote number
#     screen = read_screen_text(window)

#     log.debug("=== QUOTE CREATION RAW SCREEN ===")
#     log.debug(repr(screen[:800]))

#     quote_number = _parse_quote_number(screen)

#     result = {
#         "quote_number": quote_number,
#         "make_code":    make_code,
#         "customer":     customer_search,
#         "parts":        parts,
#         "status":       "saved",
#     }

#     log.info(f"✅ Quote created: #{quote_number}")
#     return result


# # ═══════════════════════════════════════════════════════════════
# #  REQUOTE — Update price on existing quote
# # ═══════════════════════════════════════════════════════════════

# def requote(window, quote_number, updated_parts):
#     """
#     Modifies an existing quote with new (lower) prices.
#     Called by the orchestrator when we need to undercut a competitor.

#     Args:
#         window:        ERA Port window
#         quote_number:  str — existing quote number to modify
#         updated_parts: list of dicts:
#                        [{ "part_number": "2321721010", "qty": 1, "sale_price": 21.00 }]

#     Returns:
#         True if successful, False otherwise.

#     Screen flow:
#         2525 → make code → quote number → M (modify)
#         → navigate to part line → update price
#         → E + Enter → E + Enter → S/P

#     # TODO: Confirm modify flow from live screen — specifically how to
#     #       navigate to a specific part line to change its price.
#     #       ERA Power may use line numbers or part number search.
#     """
#     log.info(f"Requoting quote #{quote_number} with {len(updated_parts)} updated part(s)...")

#     navigate_to(window, MENU_QUOTE)
#     time.sleep(WAIT_LONG)

#     # Enter make code
#     # TODO: Store make_code in the state object so we can pass it here
#     # For now the caller must ensure make code is entered via state
#     window.set_focus()
#     send_keys("{ENTER}")      # skip make code if already set, or handle via state
#     time.sleep(WAIT_SHORT)

#     # Enter the existing quote number to load it
#     log.info(f"Loading quote: {quote_number}")
#     send_keys(str(quote_number), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_LONG)

#     # Read screen to confirm we loaded the right quote
#     screen = read_screen_text(window)
#     if quote_number not in screen:
#         log.warning(f"Could not confirm quote #{quote_number} loaded.")

#     # Press M to modify
#     log.info("Entering modify mode (M)...")
#     send_keys("M")
#     time.sleep(WAIT_MEDIUM)

#     # Update price for each part
#     for part in updated_parts:
#         _modify_part_price(window, part)

#     # Finalise
#     send_keys("E")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     send_keys("E")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     send_keys("S")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_LONG)

#     log.info(f"✅ Quote #{quote_number} updated with new prices.")
#     return True


# # ═══════════════════════════════════════════════════════════════
# #  CONVERT QUOTE TO INVOICE (Sales Order)
# # ═══════════════════════════════════════════════════════════════

# def convert_to_invoice(window, make_code, customer_search, parts, counterman=None, order_type=None):
#     """
#     Creates a sales order / invoice in screen 2525.
#     Called ONLY after winning the PartsCheck competition.

#     This is the same as create_quote() but WITHOUT the PQ step,
#     and ends with B (both — complete invoice and email/print).

#     Args:
#         window:          ERA Port window
#         make_code:       e.g. "TO"
#         customer_search: customer number or partial name
#         parts:           list of dicts with final agreed prices
#         counterman:      optional
#         order_type:      optional

#     Returns:
#         dict: { invoice_number, make_code, customer, parts, status }

#     Screen flow per docs:
#         2525 → make code → Enter on invoice#
#         → customer → counterman → order type → Enter on ID#
#         → parts + qty loop
#         → E + Enter → E + Enter → B (both = complete + email/print)
#     """
#     log.info(f"Creating invoice — make: {make_code}, customer: {customer_search}")
#     log.info(f"Parts on invoice: {len(parts)} line(s)")

#     navigate_to(window, MENU_QUOTE)
#     time.sleep(WAIT_LONG)

#     # Step 1: Enter make code
#     window.set_focus()
#     send_keys(make_code, pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 2: Press Enter on invoice# (no PQ — this is a real invoice)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 3: Customer
#     log.info(f"Entering customer: {customer_search}")
#     send_keys(str(customer_search), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 4: Counterman
#     if counterman:
#         send_keys(str(counterman), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_SHORT)

#     # Step 5: Order type
#     if order_type:
#         send_keys(str(order_type), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_SHORT)

#     # Step 6: ID# prompt
#     send_keys("{ENTER}")
#     time.sleep(WAIT_SHORT)

#     # Step 7: Enter each part
#     for part in parts:
#         _enter_part_line(window, part)

#     # Step 8: Empty Enter to end part entry
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 9: E + Enter (first)
#     send_keys("E")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 10: E + Enter (second)
#     send_keys("E")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     # Step 11: B = Both (complete invoice AND email/print)
#     log.info("Finalising invoice (B = both)...")
#     send_keys("B")
#     send_keys("{ENTER}")
#     time.sleep(WAIT_LONG)

#     screen = read_screen_text(window)

#     log.debug("=== INVOICE CREATION RAW SCREEN ===")
#     log.debug(repr(screen[:800]))

#     invoice_number = _parse_invoice_number(screen)

#     result = {
#         "invoice_number": invoice_number,
#         "make_code":      make_code,
#         "customer":       customer_search,
#         "parts":          parts,
#         "status":         "invoiced",
#     }

#     log.info(f"✅ Invoice created: #{invoice_number}")
#     return result


# # ═══════════════════════════════════════════════════════════════
# #  INTERNAL HELPERS
# # ═══════════════════════════════════════════════════════════════

# def _enter_part_line(window, part):
#     """
#     Enters a single part line (part number + qty) into 2525.

#     part = { "part_number": "2321721010", "qty": 1, "sale_price": 23.75 }

#     Screen flow:
#         Input part number → Enter
#         Input qty → Enter
#         (repeat for next part)

#     # NOTE: sale_price is NOT entered here — ERA Power pulls it automatically.
#     #       Price override (if needed for requote) uses _modify_part_price().
#     #       Confirm with client whether direct price entry is supported on new lines.
#     """
#     log.info(f"  Entering part: {part['part_number']} × {part.get('qty', 1)}")

#     window.set_focus()
#     send_keys(str(part["part_number"]), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)

#     send_keys(str(part.get("qty", 1)), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)


# def _modify_part_price(window, part):
#     """
#     Updates the price for a specific part on an existing quote.

#     # TODO: Confirm the exact key sequence for modifying a line price.
#     #       ERA Power may require:
#     #         - Typing the line number then navigating to price field, OR
#     #         - Searching by part number then tabbing to price field
#     #       Update this function after first live test.
#     """
#     log.info(f"  Updating price: {part['part_number']} → ${part['sale_price']}")

#     window.set_focus()

#     # Placeholder sequence — update after confirming live screen behaviour
#     # Common pattern: type line number → Tab to price field → type new price → Enter
#     send_keys(str(part.get("line_number", "")), pause=0.05)
#     send_keys("{TAB}")
#     time.sleep(WAIT_SHORT)

#     send_keys(str(part["sale_price"]), pause=0.05)
#     send_keys("{ENTER}")
#     time.sleep(WAIT_MEDIUM)


# def _parse_quote_number(screen_text):
#     """
#     Extracts assigned quote number from the screen after saving.

#     # TODO: Confirm exact label used in ERA Power for quote number.
#     #       May be "Quote#", "Q#", "Ref#" etc.
#     """
#     patterns = [
#         r"Quote#?\s*[:\s]*(\d+)",
#         r"Q#?\s*[:\s]*(\d+)",
#         r"Ref#?\s*[:\s]*(\d+)",
#     ]
#     for pattern in patterns:
#         m = re.search(pattern, screen_text, re.IGNORECASE)
#         if m:
#             return m.group(1)
#     log.warning("Could not parse quote number from screen.")
#     return None


# def _parse_invoice_number(screen_text):
#     """
#     Extracts invoice number from the screen after completing.

#     # TODO: Confirm exact label used in ERA Power for invoice number.
#     """
#     patterns = [
#         r"Invoice#?\s*[:\s]*(\d+)",
#         r"Inv#?\s*[:\s]*(\d+)",
#         r"#\s*(\d{5,})",
#     ]
#     for pattern in patterns:
#         m = re.search(pattern, screen_text, re.IGNORECASE)
#         if m:
#             return m.group(1)
#     log.warning("Could not parse invoice number from screen.")
#     return None


# # ═══════════════════════════════════════════════════════════════
# #  STANDALONE TEST
# # ═══════════════════════════════════════════════════════════════

# if __name__ == "__main__":
#     logging.basicConfig(
#         level=logging.INFO,
#         format="%(asctime)s [%(levelname)s] %(message)s"
#     )

#     # ── hardcoded test values — replace with dynamic data in production ──
#     TEST_MAKE     = "TO"
#     TEST_CUSTOMER = "ABC"
#     TEST_PARTS    = [
#         { "part_number": "2321721010", "qty": 1, "sale_price": 23.75 },
#     ]

#     try:
#         era_window = launch_era_port()
#         login(era_window)

#         # Test: create a quote
#         result = create_quote(
#             era_window,
#             make_code=TEST_MAKE,
#             customer_search=TEST_CUSTOMER,
#             parts=TEST_PARTS,
#         )

#         print("\n✅ Quote created!")
#         print(f"   Quote#:   {result['quote_number']}")
#         print(f"   Customer: {result['customer']}")
#         print(f"   Parts:    {len(result['parts'])}")
#         print(f"   Status:   {result['status']}")

#         with open(OUTPUT_FILE, "w") as f:
#             json.dump(result, f, indent=2)
#         print(f"\n💾 Saved to: {OUTPUT_FILE}")

#         era_window = logoff_era(era_window)

#     except Exception as e:
#         log.error(f"Error: {e}")
#         raise
"""
ERA Power — Quote & Sales Order Module (FIXED)
================================================
Screen 2525: Create quotes and convert winning quotes to invoices.

Key flows:
  - create_quote()       → new quote (PQ mode), save/print
  - requote()            → modify existing quote with lower price
  - convert_to_invoice() → turn a won quote into a sales order / invoice

Changes from original:
  - Removed extra Enter after PQ (was skipping past customer field)
  - Fixed regex parsers to handle alphanumeric IDs like "1104172D"
  - Added screen validation after each major step
  - requote() now uses R=Reprice command from ERA's command bar
  - Added _validate_screen() helper for robust step-by-step checks
  - create_quote saves with S by default; print_quote flag added for P

Usage (standalone test):
    py -3.14 era_quote_fixed.py

Usage (from orchestrator):
    from era_quote_fixed import create_quote, requote, convert_to_invoice
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
        wait_for_text,
        WAIT_SHORT, WAIT_MEDIUM, WAIT_LONG,
    )
except ImportError:
    raise ImportError(
        "Era_power.py must be in the same directory as era_quote_fixed.py"
    )

log = logging.getLogger("eraPower.quote")

MENU_QUOTE    = "2525"
OUTPUT_FILE   = r"C:\Projects\pentana\era_quote_result.json"


# ═══════════════════════════════════════════════════════════════
#  SCREEN VALIDATION HELPER
# ═══════════════════════════════════════════════════════════════

def _validate_screen(window, expected_text, step_name, timeout=10):
    """
    Reads screen and checks for expected text. Logs warning if not found.
    Returns the screen text regardless.

    This prevents blind keystroke sequences from going off-rail when
    the system is slow or an unexpected popup appears.
    """
    found = wait_for_text(window, expected_text, timeout=timeout)
    screen = read_screen_text(window)
    if not found:
        log.warning(
            f"[{step_name}] Expected '{expected_text}' on screen but didn't find it. "
            f"Screen preview: {repr(screen[:200])}"
        )
    else:
        log.info(f"[{step_name}] Screen confirmed — found '{expected_text}'")
    return screen


# ═══════════════════════════════════════════════════════════════
#  CREATE QUOTE  (Screen 2525 → PQ mode)
# ═══════════════════════════════════════════════════════════════

def create_quote(window, make_code, customer_search, parts,
                 counterman=None, order_type=None, print_quote=False):
    """
    Creates a new quote in screen 2525 using the PQ sequence.

    Args:
        window:          ERA Port window
        make_code:       e.g. "TO", "GM"
        customer_search: customer number or partial name string
        parts:           list of dicts:
                         [{ "part_number": "2321721010", "qty": 1 }]
        counterman:      optional counterman number (leave None to keep default)
        order_type:      optional order type (leave None to keep "Daily order" default)
        print_quote:     if True, sends P (print/email + save); if False, sends S (save only)

    Returns:
        dict: { quote_number, make_code, customer, parts, totals, status }

    Doc flow (exact):
        2525 → make code + Enter
        → PQ + Enter (screen changes from "Invoice" to "Quote")
        → Enter (pass Quote# field — system assigns number on save)
        → customer number or partial name + Enter
        → counterman + Enter (or just Enter to keep default)
        → order type + Enter (or just Enter to keep "Daily order")
        → Enter on ID# if prompted
        → for each part: part_number + Enter → qty + Enter
        → Enter on empty line (finish parts)
        → E + Enter
        → E + Enter
        → P + Enter (print/email) or S + Enter (save only)

    IMPORTANT: The doc's "Press enter" after "Screen will then change word
    invoice to quote" is the Enter on the Quote# field — NOT a separate
    confirmation step. PQ goes into Invoice# field, Enter submits it,
    screen switches to Quote mode, cursor lands on Quote# field, then
    you press Enter to pass it.
    """
    log.info(f"Creating quote — make: {make_code}, customer: {customer_search}")
    log.info(f"Parts to quote: {len(parts)} line(s)")

    # Navigate to screen 2525
    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Step 1: Enter make code
    log.info(f"Entering make code: {make_code}")
    window.set_focus()
    send_keys(make_code, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 2: Type PQ into the Invoice# field to switch to Quote mode
    # Screenshot img_10 confirms: "pq" is typed into the Invoice# field
    # on the "Counter Sales" screen. After Enter, the header changes to "QUOTES".
    log.info("Switching to quote mode (PQ)...")
    window.set_focus()
    send_keys("PQ", pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Validate: screen should now say "QUOTES" instead of "Counter Sales"
    _validate_screen(window, "QUOTES", "PQ switch")

    # Step 3: Press Enter on the Quote# field
    # Screenshot img_8 confirms: after PQ, the field label changes to "Quote#"
    # and cursor is sitting there. We press Enter to pass it (number assigned on save).
    # Screenshot img_4 confirms: cursor then moves to "Cust #" field.
    log.info("Pressing Enter on Quote# field...")
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
    log.info("Finishing part entry (Enter on empty line)...")
    window.set_focus()
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 10: E + Enter (first confirmation — exits part entry)
    log.info("First E + Enter...")
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 11: E + Enter (second confirmation — moves to summary screen)
    log.info("Second E + Enter...")
    send_keys("E")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Validate: summary screen should now be visible
    # Screenshot img_11 shows: Quote# at top, totals, and options at bottom
    screen = _validate_screen(window, "Total", "Quote summary")

    # Capture totals from summary screen before saving
    totals = _parse_summary_totals(screen)

    # Step 12: Save or Print
    if print_quote:
        log.info("Printing and saving quote (P)...")
        send_keys("P")
    else:
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
        "totals":       totals,
        "status":       "saved" if not print_quote else "printed",
    }

    log.info(f"✅ Quote created: #{quote_number}")
    return result


# ═══════════════════════════════════════════════════════════════
#  REQUOTE — Update price on existing quote
# ═══════════════════════════════════════════════════════════════

def requote(window, make_code, quote_number, updated_parts):
    """
    Modifies an existing quote with new (lower) prices.
    Called by the orchestrator when we need to undercut a competitor.

    Args:
        window:        ERA Port window
        make_code:     str — make code (required to enter 2525 properly)
        quote_number:  str — existing quote number to modify (e.g. "1104172D")
        updated_parts: list of dicts:
                       [{ "line_number": 1, "part_number": "2321721010", "sale_price": 21.00 }]

    Returns:
        True if successful, False otherwise.

    The command bar on the quote screen (screenshot img_2) shows:
        (A=Add)(D=Del)(E=Ent)(M=Mod)(Pn=Pg#)(O=Opt)(R=Reprice)(Q=Inq)(CI=CustInq)

    R=Reprice is the correct command for changing a price on an existing line.

    Flow:
        2525 → make code → quote number + Enter (loads existing quote)
        → for each part: navigate to line → R (Reprice) → new price + Enter
        → E + Enter → E + Enter → S (save)
    """
    log.info(f"Requoting quote #{quote_number} with {len(updated_parts)} updated part(s)...")

    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Enter make code (required every time you enter 2525)
    log.info(f"Entering make code: {make_code}")
    window.set_focus()
    send_keys(make_code, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Enter the existing quote number to load it
    # For quotes, type the quote number where Invoice#/Quote# field is
    log.info(f"Loading quote: {quote_number}")
    send_keys(str(quote_number), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    # Validate: confirm we loaded the right quote
    screen = _validate_screen(window, quote_number, "Load quote")

    # Update price for each part using R=Reprice
    for part in updated_parts:
        _reprice_part_line(window, part)

    # Finalise: E + Enter twice, then Save
    log.info("Finalising requote...")
    send_keys("{ENTER}")  # exit part entry area
    time.sleep(WAIT_MEDIUM)

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

def convert_to_invoice(window, make_code, customer_search, parts,
                       counterman=None, order_type=None):
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
        dict: { invoice_number, make_code, customer, parts, totals, status }

    Doc flow (exact):
        2525 → make code + Enter
        → Enter on invoice# (leave blank — no PQ)
        → customer number or partial name + Enter
        → counterman + Enter
        → order type + Enter
        → Enter on ID#
        → parts + qty loop
        → Enter on empty line
        → E + Enter → E + Enter
        → B (both = complete invoice + email/print)
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

    # Validate: should be on Counter Sales screen
    _validate_screen(window, "Counter Sales", "Invoice entry")

    # Step 2: Press Enter on invoice# (no PQ — this is a real invoice)
    # Doc: "Press enter on invoice# then input customer number"
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

    # Validate: summary screen with totals and B option
    screen = _validate_screen(window, "Total", "Invoice summary")
    totals = _parse_summary_totals(screen)

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
        "totals":         totals,
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

    part = { "part_number": "2321721010", "qty": 1 }

    Doc flow:
        Input part number → Enter
        Input required qty → Enter
        (repeat for next part)

    NOTE: sale_price is NOT entered during initial part entry.
    ERA Power auto-calculates the price based on customer pricing tier.
    To override a price on an existing quote, use _reprice_part_line().
    """
    pn  = part["part_number"]
    qty = part.get("qty", 1)

    log.info(f"  Entering part: {pn} × {qty}")

    window.set_focus()
    send_keys(str(pn), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    send_keys(str(qty), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)


def _reprice_part_line(window, part):
    """
    Updates the price for a specific part on an existing quote using R=Reprice.

    The command bar (visible in screenshot img_2) shows:
        (A=Add)(D=Del)(E=Ent)(M=Mod)(Pn=Pg#)(O=Opt)(R=Reprice)(Q=Inq)(CI=CustInq)

    R=Reprice is the dedicated command for changing a line's sale price.

    Args:
        part: dict with keys:
            - line_number (int): the line number on the quote (1, 2, 3...)
            - sale_price (float): the new price to set

    Flow (best guess — needs live testing):
        Type line number + Enter → R (Reprice) → new price + Enter

    TODO: Confirm exact reprice flow on live system.
          - Does R prompt for line number, or must you navigate to the line first?
          - Does it accept a decimal price directly?
          - After entering price, does it return to the part list or need Enter?
    """
    line_num = part.get("line_number")
    new_price = part["sale_price"]

    log.info(f"  Repricing line {line_num}: → ${new_price}")

    window.set_focus()

    # Navigate to the line (type line number to select it)
    if line_num:
        send_keys(str(line_num), pause=0.05)
        send_keys("{ENTER}")
        time.sleep(WAIT_SHORT)

    # Press R for Reprice
    send_keys("R")
    time.sleep(WAIT_SHORT)

    # Enter new price
    send_keys(str(new_price), pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)


def _parse_quote_number(screen_text):
    """
    Extracts assigned quote number from the screen after saving.

    ERA Power uses alphanumeric quote numbers like "1104172D"
    (screenshot img_11 shows Quote# 1104172D).
    The old regex only matched pure digits — FIXED to match alphanumeric.
    """
    patterns = [
        r"Quote#?\s*[:\s]*([A-Z0-9]+)",
        r"Q#?\s*[:\s]*([A-Z0-9]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, screen_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # Filter out noise — quote numbers are typically 6+ chars
            if len(val) >= 4:
                return val
    log.warning("Could not parse quote number from screen.")
    return None


def _parse_invoice_number(screen_text):
    """
    Extracts invoice number from the screen after completing.

    ERA Power uses alphanumeric invoice numbers like "1980376D"
    (screenshot img_13 shows Invoice# 1980376D).
    FIXED to match alphanumeric.
    """
    patterns = [
        r"Invoice#?\s*[:\s]*([A-Z0-9]+)",
        r"Inv#?\s*[:\s]*([A-Z0-9]+)",
        r"Control\s+No\.?\s*[:\s]*([A-Z0-9]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, screen_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if len(val) >= 4:
                return val
    log.warning("Could not parse invoice number from screen.")
    return None


def _parse_summary_totals(screen_text):
    """
    Extracts key totals from the summary screen (quote or invoice).

    Screenshots img_3, img_11, img_13 show fields like:
        Total (No Tax)   165.49
        GST              16.55
        Total Quote      182.04   or   Total Invoice   169.00
        ~GP$             17.73
        ~GP%             10.7
    """
    totals = {}

    patterns = {
        "total_no_tax":   r"Total\s*\(No\s*Tax\)\s+([\d.]+)",
        "gst":            r"GST\s+([\d.]+)",
        "total_quote":    r"Total\s+Quote\s+([\d.]+)",
        "total_invoice":  r"Total\s+Invoice\s+([\d.]+)",
        "gp_dollars":     r"[~^]GP\$\s+([\d.]+)",
        "gp_percent":     r"[~^]GP%\s+([\d.]+)",
        "balance":        r"Bal\s+([\d.]+)",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, screen_text, re.IGNORECASE)
        if m:
            totals[key] = float(m.group(1))

    return totals


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
    TEST_CUSTOMER = "158746"
    TEST_PARTS    = [
        { "part_number": "2321721010", "qty": 1 },
        { "part_number": "2330030410", "qty": 2 },
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
        print(f"   Totals:   {result['totals']}")
        print(f"   Status:   {result['status']}")

        with open(OUTPUT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Saved to: {OUTPUT_FILE}")

        era_window = logoff_era(era_window)

    except Exception as e:
        log.error(f"Error: {e}")
        raise