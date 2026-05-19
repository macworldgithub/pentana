"""
eraPower Automation Module
==========================
Controls the ERA Port terminal window using pywinauto.
Handles login, navigation, parts inquiry, and quoting.
Auto-launches ERA Port if not already running.

Requirements:
    py -3.14 -m pip install pywinauto pywin32 pyautogui pillow
"""

import time
import re
import logging
import subprocess
import os
import json
import win32con
import win32api
import win32clipboard
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
ERA_USERNAME       = "partscounter"
ERA_PASSWORD       = "ap15cu6"
ERA_WORKSTATION_ID = "429"

# TODO: Update this path to the actual ERA Port executable on this machine
# Common locations:
#   C:\Program Files\Ericom Software\PowerTerm\ptw32.exe
#   C:\Program Files (x86)\ERA Port\eraport.exe
#   C:\ERALink\ERALink1.wic  (session file — double-click to open)
ERA_PORT_EXE  = r"C:\Program Files (x86)\ERALink Plus\wInteg.exe"
ERA_PORT_WAIT = 5  # seconds to wait for ERA Port to launch

# Menu selection codes
MENU_PARTS_INQUIRY = "2021"
MENU_QUOTE         = "2525"
MENU_SUPPLIER      = "2140"

# Timing — increase if system is slow
WAIT_SHORT  = 0.5
WAIT_MEDIUM = 1.0
WAIT_LONG   = 2.0

# ─────────────────────────────────────────────
#  MAKE CODES
# ─────────────────────────────────────────────
MAKE_CODES = {
    "toyota":         "TO",
    "holden":         "GM",
    "mercedes":       "MB",
    "mercedes-benz":  "MB",
    "isuzu":          "IS",
    "isuzu ute":      "IA",
    "bosch":          "BO",
    "non genuine":    "NG",
    "western star":   "WS",
    "man":            "MA",
    "detroit diesel": "DE",
    "honda":          "HO",
    "jac":            "JU",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("eraPower")


# ═══════════════════════════════════════════════════════════════
#  WINDOW HELPERS
# ═══════════════════════════════════════════════════════════════

def find_era_window():
    """
    Finds the ERA Port window regardless of the session number in the title.
    Title always contains 'ERA Port' and '172.16.2.1 Windows Sockets Open'.
    Returns a pywinauto WindowSpecification or raises RuntimeError.
    """
    log.info("Searching for ERA Port window...")
    desktop = Desktop(backend="uia")
    windows = desktop.windows()

    for win in windows:
        try:
            title = win.window_text()
            # Match regardless of Open/Closed state in title
            if "ERA Port" in title and "172.16.2.1 Windows Sockets" in title:
                log.info(f"Found ERA Port window: {title}")
                app = Application(backend="uia").connect(handle=win.handle)
                return app.window(handle=win.handle)
        except Exception:
            continue

    raise RuntimeError(
        "ERA Port window not found. Make sure ERA Port is open and connected."
    )


def type_and_enter(window, text, wait=WAIT_MEDIUM):
    """Types text into the active ERA Port window and presses Enter."""
    window.set_focus()
    time.sleep(WAIT_SHORT)
    send_keys(text, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(wait)


def read_screen_text(window):
    """
    Reads visible screen text from ERA Port terminal using:
      Alt+E → W (Select Window) → Alt+E → C (Copy) → clipboard
    'Select Window' copies only visible screen, not the entire scroll buffer.
    Confirmed working on ERA Port terminal emulator.
    """
    try:
        import pyautogui
        pyautogui.FAILSAFE = False

        # Click center of ERA Port to ensure it has focus
        rect = window.rectangle()
        center_x = (rect.left + rect.right) // 2
        center_y = (rect.top + rect.bottom) // 2
        pyautogui.click(center_x, center_y)
        time.sleep(0.8)

        # Alt+E → W = Select Window (visible screen only, not scroll buffer)
        pyautogui.hotkey('alt', 'e')
        time.sleep(0.6)
        pyautogui.press('w')
        time.sleep(0.4)

        # Alt+E → C = Copy
        pyautogui.hotkey('alt', 'e')
        time.sleep(0.6)
        pyautogui.press('c')
        time.sleep(0.5)

        # Read from clipboard
        win32clipboard.OpenClipboard()
        try:
            text = win32clipboard.GetClipboardData(win32con.CF_TEXT)
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        finally:
            win32clipboard.CloseClipboard()

        log.debug(f"Screen text captured ({len(text)} chars)")
        return text

    except ImportError:
        log.error("pyautogui not installed. Run: py -3.14 -m pip install pyautogui")
        return ""
    except Exception as e:
        log.warning(f"Could not read screen text: {e}")
        return ""


def wait_for_text(window, expected_text, timeout=10, interval=0.5):
    """
    Polls the screen until expected_text appears or timeout is reached.
    Returns True if found, False if timed out.
    """
    elapsed = 0
    while elapsed < timeout:
        screen = read_screen_text(window)
        if expected_text in screen:
            return True
        time.sleep(interval)
        elapsed += interval
    log.warning(f"Timed out waiting for: '{expected_text}'")
    return False


# ═══════════════════════════════════════════════════════════════
#  LOGIN FLOW
# ═══════════════════════════════════════════════════════════════

def login(window):
    """
    Handles the full login sequence using blind typing.
    We know the exact sequence of prompts so we don't need to read the screen.

    Sequence:
      1. h558 login:          -> type username + Enter
      2. Password:            -> type password + Enter
      3. Workstation ID:      -> type 429 + Enter
      4. Notification screen  -> press Enter to dismiss (if present)
      5. Main menu            -> ready
    """
    log.info("Starting login sequence (blind typing mode)...")

    window.set_focus()
    time.sleep(WAIT_MEDIUM)

    # Step 1: Type username
    log.info("Entering username...")
    send_keys(ERA_USERNAME, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 2: Type password
    log.info("Entering password...")
    send_keys(ERA_PASSWORD, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Step 3: Type workstation ID
    log.info(f"Entering workstation ID: {ERA_WORKSTATION_ID}")
    send_keys(ERA_WORKSTATION_ID, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    # Step 4: Dismiss notification screen if present
    # Safe to always press Enter here — if no notification it goes to main menu anyway
    log.info("Dismissing notification screen (if any)...")
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)

    log.info("Login sequence complete. Should be at main menu now.")
    return True


# ═══════════════════════════════════════════════════════════════
#  NAVIGATION
# ═══════════════════════════════════════════════════════════════

def navigate_to(window, menu_code):
    """
    Types a menu selection code and presses Enter.
    Use this to navigate to any screen (2021, 2525, 2140, etc.)
    """
    log.info(f"Navigating to menu: {menu_code}")
    window.set_focus()
    time.sleep(WAIT_SHORT)
    send_keys(menu_code, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)


def launch_era_port():
    """
    Launches ERA Port if it's not already running.
    Waits for the login screen to appear before returning.
    Returns the ERA Port window.
    """
    # Check if already running
    try:
        window = find_era_window()
        log.info("ERA Port already running — reusing existing window.")
        return window
    except RuntimeError:
        pass

    log.info(f"Launching ERA Port from: {ERA_PORT_EXE}")
    if not os.path.exists(ERA_PORT_EXE):
        raise FileNotFoundError(
            f"ERA Port executable not found at: {ERA_PORT_EXE}\n"
            f"Update ERA_PORT_EXE in the config section at the top of this file."
        )

    subprocess.Popen([ERA_PORT_EXE], shell=True)
    log.info(f"Waiting {ERA_PORT_WAIT}s for ERA Port to start...")
    time.sleep(ERA_PORT_WAIT)

    # Find the window after launch
    window = find_era_window()
    log.info("ERA Port launched successfully.")
    return window


# def go_to_main_menu(window):
#     """
#     Returns to the main menu from any screen.
#     Sends ESC multiple times then navigates to main menu selection.
#     """
#     log.info("Returning to main menu...")
#     window.set_focus()
#     # Send ESC 3 times to back out of any sub-menu
#     for _ in range(3):
#         send_keys("{ESC}")
#         time.sleep(WAIT_SHORT)
#     time.sleep(WAIT_MEDIUM)

def logoff_era(window):
    import subprocess
    log.info("Closing ERA Port...")
    try:
        window.close()
        time.sleep(2)
    except Exception:
        pass
    subprocess.call(["taskkill", "/f", "/im", "wInteg.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    log.info("Relaunching ERA Port...")
    os.startfile(ERA_PORT_EXE)
    time.sleep(ERA_PORT_WAIT)
    return find_era_window()

# ═══════════════════════════════════════════════════════════════
#  PARTS INQUIRY  (Menu 2021)
# ═══════════════════════════════════════════════════════════════

def lookup_part(window, make_code, part_number):
    """
    Navigates to Parts Inquiry (2021), looks up a part, and returns pricing.

    Args:
        window:      ERA Port window
        make_code:   e.g. "TO", "GM", "MB"
        part_number: e.g. "2321721010"

    Returns:
        dict with keys: part_number, description, avail, sale_price, list_price
        Returns None if part not found.
    """
    log.info(f"Looking up part: {make_code} / {part_number}")

    # Navigate to parts inquiry and wait for screen to fully load
    navigate_to(window, MENU_PARTS_INQUIRY)
    time.sleep(WAIT_LONG)  # wait for Parts Counter screen to appear

    # Enter Make code
    log.info(f"Entering make code: {make_code}")
    window.set_focus()
    send_keys(make_code, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    # Enter Part number
    log.info(f"Entering part number: {part_number}")
    window.set_focus()
    send_keys(part_number, pause=0.05)
    send_keys("{ENTER}")
    time.sleep(WAIT_LONG)  # wait for results to load

    # Now read the screen ONCE — no polling loop
    screen = read_screen_text(window)

    # DEBUG: print raw screen
    print("=== RAW SCREEN TEXT ===")
    print(repr(screen[:800]))
    print("=======================")

    # Parse the pricing from screen
    result = parse_parts_result(screen, part_number)

    if result:
        log.info(f"Part found — Sale: {result['sale_price']}, List: {result['list_price']}")
    else:
        log.warning(f"Part {part_number} not found or could not parse price.")

    return result


# def parse_parts_result(screen_text, part_number):
#     """
#     Parses the Parts Inquiry result screen to extract pricing.

#     Screen layout example:
#         1  2321721010    FILTER SUCT 2221
#               3 CAR2            23.75    21.59
#               0/0               370      T4    5

#     Returns dict or None.

#     # TODO: If eraPower screen layout changes, update the regex patterns below
#     """
#     try:
#         lines = screen_text.split("\n")

#         description = ""
#         sale_price  = None
#         list_price  = None
#         avail       = None

#         for i, line in enumerate(lines):
#             # Find the line containing our part number
#             if part_number in line:
#                 # Description is on the same line after the part number
#                 desc_match = re.search(
#                     rf"{re.escape(part_number)}\s+(.+)", line
#                 )
#                 if desc_match:
#                     description = desc_match.group(1).strip()

#                 # Price line is typically the next line
#                 # Format: "   3 CAR2   <spaces>   23.75    21.59"
#                 if i + 1 < len(lines):
#                     price_line = lines[i + 1]
#                     prices = re.findall(r"\d+\.\d{2}", price_line)
#                     if len(prices) >= 2:
#                         sale_price = float(prices[0])
#                         list_price = float(prices[1])
#                     elif len(prices) == 1:
#                         sale_price = float(prices[0])

#                 # Availability — look for pattern like "3 CAR2"
#                 avail_match = re.search(r"(\d+)\s+[A-Z]{2,}", price_line if i + 1 < len(lines) else "")
#                 if avail_match:
#                     avail = int(avail_match.group(1))

#                 break

#         if sale_price is None:
#             return None

#         return {
#             "part_number":  part_number,
#             "description":  description,
#             "avail":        avail,
#             "sale_price":   sale_price,
#             "list_price":   list_price,
#         }

#     except Exception as e:
#         log.error(f"Error parsing parts result: {e}")
#         return None

def parse_parts_result(screen_text, part_number):
    try:
        lines = screen_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        description = ""
        sale_price  = None
        list_price  = None
        avail       = None

        for i, line in enumerate(lines):
            if part_number in line and not line.strip().startswith("Part#"):
                desc_match = re.search(rf"{re.escape(part_number)}\s+(.+)", line)
                if desc_match:
                    description = desc_match.group(1).strip()
                if i + 1 < len(lines):
                    price_line = lines[i + 1]
                    prices = re.findall(r"\d+\.\d{2}", price_line)
                    if len(prices) >= 2:
                        sale_price = float(prices[0])
                        list_price = float(prices[1])
                    elif len(prices) == 1:
                        sale_price = float(prices[0])
                    avail_match = re.search(r"(\d+)\s+[A-Z]{2,4}", price_line)
                    if avail_match:
                        avail = int(avail_match.group(1))
                break

        if sale_price is None:
            return None

        return {
            "part_number":  part_number,
            "description":  description,
            "avail":        avail,
            "sale_price":   sale_price,
            "list_price":   list_price,
        }
    except Exception as e:
        log.error(f"Error parsing parts result: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
#  QUOTE MANAGEMENT  (Menu 2525)
# ═══════════════════════════════════════════════════════════════

def create_quote(window, customer_name, make_code, parts):
    """
    Creates a NEW quote in menu 2525.

    Args:
        window:        ERA Port window
        customer_name: Customer name string
        make_code:     e.g. "TO"
        parts:         list of dicts: [{"part_number": "...", "qty": 1, "sale_price": 23.75}]

    Returns:
        quote_number (str) if successful, None otherwise.

    # TODO: Update customer fields (Cust#, Phone, Pay, Tax EX#, ID#) once
    #       client confirms what data comes from PartsCheck orders
    """
    log.info(f"Creating new quote for: {customer_name}")

    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Press 'A' to Add a new quote
    window.set_focus()
    send_keys("A")
    time.sleep(WAIT_MEDIUM)

    # Enter Make code
    # TODO: Confirm field tab order on quote creation screen
    type_and_enter(window, make_code, wait=WAIT_SHORT)

    # Add each part line
    for part in parts:
        _add_part_line_to_quote(window, part)

    # TODO: Capture the assigned quote number from the screen
    # The quote number appears at top left of the screen after creation
    screen = read_screen_text(window)
    quote_number = _parse_quote_number(screen)

    log.info(f"Quote created: #{quote_number}")
    return quote_number


def modify_quote(window, quote_number, parts):
    """
    Modifies an EXISTING quote with new (lower) prices.
    Used for the re-quote after price reveal.

    Args:
        window:       ERA Port window
        quote_number: existing quote number string
        parts:        list of dicts with updated sale_price values

    # TODO: Update re-quote price logic once client confirms minimum margin rules
    #       Currently just uses whatever price is passed in
    """
    log.info(f"Modifying quote #{quote_number} with new prices...")

    navigate_to(window, MENU_QUOTE)
    time.sleep(WAIT_LONG)

    # Enter existing quote number to load it
    type_and_enter(window, quote_number, wait=WAIT_MEDIUM)

    # Press 'M' to Modify
    window.set_focus()
    send_keys("M")
    time.sleep(WAIT_MEDIUM)

    # Update each part line price
    for part in parts:
        _modify_part_line_price(window, part)

    log.info(f"Quote #{quote_number} updated successfully.")
    return True


def _add_part_line_to_quote(window, part):
    """
    Adds a single part line to an open quote.
    part = {"part_number": "2321721010", "qty": 1, "sale_price": 23.75}

    # TODO: Confirm exact key sequence for adding a part line in 2525
    #       This may need adjustment based on actual screen field order
    """
    log.info(f"Adding part line: {part['part_number']} @ {part['sale_price']}")

    window.set_focus()
    send_keys("A")          # A=Add line
    time.sleep(WAIT_SHORT)

    send_keys(part["part_number"])
    send_keys("{TAB}")
    time.sleep(WAIT_SHORT)

    send_keys(str(part.get("qty", 1)))
    send_keys("{TAB}")
    time.sleep(WAIT_SHORT)

    send_keys(str(part["sale_price"]))
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)


def _modify_part_line_price(window, part):
    """
    Updates the price on an existing part line in a quote.

    # TODO: Confirm key sequence for modifying a line price in 2525
    """
    log.info(f"Updating price for {part['part_number']} to {part['sale_price']}")

    window.set_focus()
    send_keys("M")          # M=Modify
    time.sleep(WAIT_SHORT)

    # Navigate to the correct line and update price
    # TODO: May need to search/select the correct line by part number first
    send_keys(str(part["sale_price"]))
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)


def _parse_quote_number(screen_text):
    """
    Extracts the quote number from the 2525 screen.
    # TODO: Confirm exact format of quote number on screen
    """
    match = re.search(r"Quote#\s*[:\s]*(\d+)", screen_text)
    if match:
        return match.group(1)
    return None


def convert_invoice_to_quote(window):
    """
    Converts an invoice to a quote using the PQ sequence.
    Flow: type 'PQ' → Enter → type 'PQ' again → Enter
    """
    log.info("Converting invoice to quote (PQ sequence)...")
    window.set_focus()

    send_keys("PQ")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    send_keys("PQ")
    send_keys("{ENTER}")
    time.sleep(WAIT_MEDIUM)

    log.info("Invoice converted to quote.")


# ═══════════════════════════════════════════════════════════════
#  PRICING LOGIC
# ═══════════════════════════════════════════════════════════════

def get_quote_price(part_info):
    """
    Determines what price to quote initially.
    Currently uses Sale price from eraPower.

    # TODO: Update this logic once client confirms pricing rules, e.g:
    #   - Minimum margin percentage
    #   - Whether to use Sale or a calculated price
    #   - Any brand-specific pricing rules
    """
    return part_info["sale_price"]


def get_requote_price(part_info, competitor_prices):
    """
    Determines the re-quote price after reveal.
    Called 1 minute after prices are revealed.

    Args:
        part_info:         dict from lookup_part()
        competitor_prices: list of competitor prices (floats) from PartsCheck

    Returns:
        new_price (float) or None if we shouldn't requote

    # TODO: This is the core business logic — update with client's rules:
    #   - How much lower than the lowest competitor?
    #   - Is there a floor price / minimum margin to protect?
    #   - Should we only requote if we're not already the lowest?
    """
    if not competitor_prices:
        return None

    lowest_competitor = min(competitor_prices)
    our_current_price = part_info["sale_price"]

    # If we're already the lowest, no need to requote
    if our_current_price <= lowest_competitor:
        log.info("We are already the lowest price. No requote needed.")
        return None

    # TODO: Replace this with actual margin/floor logic from client
    # Placeholder: go $0.50 below the lowest competitor
    new_price = round(lowest_competitor - 0.50, 2)

    log.info(f"Requote price calculated: {new_price} (competitor low: {lowest_competitor})")
    return new_price


# ═══════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT  (for testing eraPower alone)
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Test script: auto-launches ERA Port, logs in, looks up a part,
    saves result to JSON, then returns to main menu.
    """
    # Output file for part lookup results
    # This JSON file is how eraPower results are shared with other modules (e.g. PartsCheck bot)
    OUTPUT_FILE = r"C:\Projects\pentana\era_results.json"

    try:
        # Step 1: Launch ERA Port (or reuse if already open)
        era_window = launch_era_port()

        # Step 2: Login
        login(era_window)

        # Step 3: Look up a test part
        # TODO: Replace with dynamic part numbers from PartsCheck orders
        result = lookup_part(era_window, "TO", "2321721010")

        if result:
            print("\n✅ Part lookup successful!")
            print(f"   Part#:       {result['part_number']}")
            print(f"   Description: {result['description']}")
            print(f"   Available:   {result['avail']}")
            print(f"   Sale Price:  ${result['sale_price']}")
            print(f"   List Price:  ${result['list_price']}")

            # Save result to JSON for use by other modules
            with open(OUTPUT_FILE, "w") as f:
                json.dump(result, f, indent=2)
            print(f"\n💾 Result saved to: {OUTPUT_FILE}")

        else:
            print("❌ Part not found.")

        # Step 4: Return to main menu ready for next task
        era_window = logoff_era(era_window)
        log.info("Returned to main menu. Ready for next task.")

    except FileNotFoundError as e:
        log.error(str(e))
    except Exception as e:
        log.error(f"Error: {e}")
        raise