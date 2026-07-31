"""
PartsCheck Automation Script
------------------------------
- Fully automatic — no manual steps needed
- Goes to login page, clicks "Login as Pakenham Mahindra"
- Every 2 minutes checks for New Quote Requests
- If found, opens the panel and clicks each quote entry

Requirements:
    pip install playwright
    playwright install chromium

Run:
    python partscheck_automation.py
"""

import asyncio
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

LOGIN_URL    = "https://www.partscheck.com.au/global/login.php"
DASHBOARD_URL = "https://www.partscheck.com.au/app/dashboard.php"
CHECK_INTERVAL_SECONDS = 120  # 2 minutes

# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

async def auto_login(page):
    """Navigate to login page and click the remembered-account button."""
    print("🌐 Navigating to PartsCheck login page...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    # Wait for the "Login as Pakenham Mahindra" button to appear
    try:
        login_btn = await page.wait_for_selector(
            "#loginRememberMeButton",
            timeout=15_000
        )
        btn_text = await login_btn.inner_text()
        print(f"  🖱️  Found button: '{btn_text.strip()}' — clicking...")
        await login_btn.click()
    except PlaywrightTimeoutError:
        print("  ⚠️  'Login as Pakenham Mahindra' button not found.")
        print("      The site may have cleared your saved session.")
        print("      Please log in manually in the browser window.")

    # Either way, wait until we land on the dashboard
    print("  ⏳ Waiting for dashboard to load...")
    await page.wait_for_selector(".toplisttext", timeout=60_000)
    print("  ✅ Logged in! Dashboard is ready.\n")


# ─────────────────────────────────────────────
# SESSION CHECK / RE-LOGIN
# ─────────────────────────────────────────────

async def ensure_logged_in(page):
    """If we've been kicked to the login page, log in again automatically."""
    current_url = page.url
    if "login.php" in current_url or "index.php" in current_url:
        print("  🔄 Session expired — logging in again automatically...")
        await auto_login(page)


# ─────────────────────────────────────────────
# QUOTE COUNTER
# ─────────────────────────────────────────────

async def get_new_quote_count(page):
    """Read the counter badge next to 'New Quote Request'."""
    try:
        counter = await page.query_selector("#counter_quoteNew")
        if counter is None:
            return 0
        class_list = await counter.get_attribute("class") or ""
        if "hide" in class_list:
            return 0
        text = await counter.inner_text()
        return int(text.strip()) if text.strip().isdigit() else 0
    except Exception as e:
        print(f"  ⚠️  Could not read quote counter: {e}")
        return 0


# ─────────────────────────────────────────────
# CLICK NEW QUOTE REQUEST
# ─────────────────────────────────────────────

async def click_new_quote_request(page):
    """Click the 'New Quote Request' tile to open the colorbox popup."""
    try:
        elements = await page.query_selector_all(".toplist.cboxlink")
        for el in elements:
            text = await el.inner_text()
            if "New Quote Request" in text:
                await el.click()
                print("  🖱️  Clicked 'New Quote Request'")
                return True
        print("  ⚠️  Could not find 'New Quote Request' button")
        return False
    except Exception as e:
        print(f"  ⚠️  Error clicking New Quote Request: {e}")
        return False


# ─────────────────────────────────────────────
# HANDLE QUOTES IN POPUP
# ─────────────────────────────────────────────

async def handle_quotes_in_popup(page):
    """
    Once the colorbox popup opens (it loads an iframe with the quotes list),
    find every quote row and click its open button.
    """
    try:
        print("  ⏳ Waiting for quotes popup...")
        await page.wait_for_selector("#colorbox", timeout=10_000)

        # Colorbox loads the quotes inside an <iframe>
        iframe_element = await page.query_selector("#cboxContent iframe")
        if iframe_element is None:
            print("  ⚠️  No iframe found inside colorbox")
            return

        frame = await iframe_element.content_frame()
        if frame is None:
            print("  ⚠️  Could not access iframe content")
            return

        # Wait for quote rows inside the iframe
        await frame.wait_for_selector(".requestRow", timeout=10_000)
        quote_rows = await frame.query_selector_all(".requestRow")
        print(f"  📋 Found {len(quote_rows)} quote(s)")

        for i, row in enumerate(quote_rows):
            try:
                # Quote number
                quote_link = await row.query_selector(".ab")
                quote_num = (await quote_link.inner_text()).strip() if quote_link else f"#{i+1}"

                # Label e.g. "Direct Purchase"
                label_el = await row.query_selector("b")
                label = (await label_el.inner_text()).strip() if label_el else "Quote"

                print(f"  🖱️  Opening quote {quote_num} — {label}...")

                # Click the green open-icon button in the row
                open_btn = await row.query_selector("td.bbG a[onclick]")
                if open_btn:
                    await open_btn.click()
                    await asyncio.sleep(1.5)
                else:
                    print(f"    ⚠️  No open button found for quote {quote_num}")

            except Exception as e:
                print(f"    ⚠️  Error on quote row {i+1}: {e}")

        print("  ✅ All quotes processed")

    except PlaywrightTimeoutError:
        print("  ⚠️  Quotes popup did not appear in time")
    except Exception as e:
        print(f"  ⚠️  Error in popup handler: {e}")


# ─────────────────────────────────────────────
# CLOSE POPUP
# ─────────────────────────────────────────────

async def close_popup(page):
    """Close the colorbox if it's visible."""
    try:
        close_btn = await page.query_selector("#cboxClose")
        if close_btn and await close_btn.is_visible():
            await close_btn.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass


# ─────────────────────────────────────────────
# ONE CHECK CYCLE
# ─────────────────────────────────────────────

async def run_check_cycle(page, cycle_number):
    """Full cycle: check session → count quotes → handle if any."""
    print(f"🔍 [{time.strftime('%H:%M:%S')}] Cycle #{cycle_number}")

    await ensure_logged_in(page)

    count = await get_new_quote_count(page)

    if count > 0:
        print(f"  🔔 {count} new quote(s) found!")
        clicked = await click_new_quote_request(page)
        if clicked:
            await handle_quotes_in_popup(page)
            await asyncio.sleep(2)
            await close_popup(page)
    else:
        print(f"  💤 No new quotes.")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

async def main():
    async with async_playwright() as p:

        # Launch visible browser (change headless=True to run in background)
        browser = await p.chromium.launch(headless=False, slow_mo=150)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        print("=" * 55)
        print("  PartsCheck Automation — Fully Automatic")
        print("=" * 55)

        # Step 1: Auto login
        await auto_login(page)

        # Step 2: Loop every 2 minutes
        cycle = 1
        while True:
            try:
                await run_check_cycle(page, cycle)
            except Exception as e:
                print(f"  ⚠️  Unexpected error in cycle {cycle}: {e}")

            cycle += 1
            print(f"  ⏱️  Next check in {CHECK_INTERVAL_SECONDS // 60} min...\n")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())