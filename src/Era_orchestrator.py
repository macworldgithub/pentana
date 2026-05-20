"""
ERA Power — Orchestrator
=========================
Ties all ERA Power modules together into one pipeline.

Handles:
  - Single ERA Power session (queue-safe for multiple concurrent offers)
  - Per-offer state objects
  - Price comparison logic
  - Requote loop with max attempt cap
  - Invoice creation only after confirmed win

Architecture:
  Each PartsCheck offer becomes a "job" dict.
  Jobs are queued and processed one at a time through ERA Power.
  PartsCheck interaction (submit price, wait for reveal, read result)
  is handled by the separate partscheck.py module (to be built).

Usage:
    py -3.14 era_orchestrator.py                  # runs test with hardcoded jobs
    from era_orchestrator import Orchestrator      # import into partscheck module

Directory layout expected:
    era_power.py          ← original (parts inquiry + helpers)
    era_customer.py       ← customer lookup
    era_supplier.py       ← supplier lookup
    era_quote.py          ← quote + invoice
    era_orchestrator.py   ← this file
"""

import time
import json
import queue
import logging
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from Era_power    import launch_era_port, login, logoff_era, lookup_part, MAKE_CODES
from Era_customer import lookup_customer, select_customer
from Era_supplier import lookup_supplier, select_supplier
from Era_quote    import create_quote, requote, convert_to_invoice

log = logging.getLogger("eraPower.orchestrator")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ── Configuration ────────────────────────────────────────────────────────────
MAX_REQUOTES   = 3          # max times we'll lower our price per offer
RESULTS_FILE   = r"C:\Projects\pentana\era_results_log.json"


# ═══════════════════════════════════════════════════════════════
#  JOB / STATE OBJECT
# ═══════════════════════════════════════════════════════════════

@dataclass
class OfferJob:
    """
    Represents one PartsCheck offer going through the full pipeline.
    One of these per active offer. Orchestrator holds the list.

    Fields populated at each stage:
      Stage 1 (ERA Power lookup):   our_cost, our_sell_price, floor_price
      Stage 2 (PartsCheck submit):  partscheck_offer_id, submitted_price
      Stage 3 (Price reveal):       competitor_prices, lowest_competitor
      Stage 4 (Decision):           won / requote / walk_away
      Stage 5 (Invoice):            quote_number, invoice_number
    """
    # Input — from PartsCheck (hardcoded for now, dynamic later)
    offer_id:         str   = ""
    make:             str   = ""          # e.g. "toyota"
    part_number:      str   = ""
    qty:              int   = 1
    customer_search:  str   = ""          # name or number

    # Derived — from ERA Power lookup
    make_code:        str   = ""          # e.g. "TO"
    description:      str   = ""
    our_sell_price:   float = 0.0
    our_list_price:   float = 0.0
    floor_price:      float = 0.0         # minimum we'll sell at
    avail:            int   = 0

    # PartsCheck state
    submitted_price:      float = 0.0
    partscheck_offer_id:  str   = ""
    competitor_prices:    List[float] = field(default_factory=list)
    lowest_competitor:    float = 0.0

    # Quote / invoice
    quote_number:    Optional[str] = None
    invoice_number:  Optional[str] = None

    # Control
    requote_attempts: int  = 0
    status:           str  = "pending"    # pending | quoted | won | lost | walked | invoiced | error
    started_at:       str  = ""
    finished_at:      str  = ""
    notes:            str  = ""


# ═══════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

class Orchestrator:
    """
    Single ERA Power session. Processes jobs from a queue one at a time.

    If ERA Power turns out to support multiple sessions, replace the
    single _window with a pool and remove the queue — each job gets
    its own window. The job/state logic stays identical.
    """

    def __init__(self):
        self._window    = None
        self._job_queue = queue.Queue()
        self._results   = []
        self._lock      = threading.Lock()
        self._running   = False

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self):
        """Launch ERA Power, log in, start processing queue."""
        log.info("Starting orchestrator...")
        self._window  = launch_era_port()
        login(self._window)
        self._running = True
        log.info("ERA Power ready. Orchestrator running.")

    def stop(self):
        """Shut down ERA Power and save results log."""
        self._running = False
        log.info("Stopping orchestrator...")
        if self._window:
            self._window = logoff_era(self._window)
        self._save_results()
        log.info("Orchestrator stopped.")

    def add_job(self, job: OfferJob):
        """
        Add a new offer job to the queue.
        Called by the PartsCheck module when a new offer is detected.
        """
        job.started_at = datetime.now().isoformat()
        log.info(f"Job queued: {job.offer_id} — {job.make} {job.part_number}")
        self._job_queue.put(job)

    def run_loop(self):
        """
        Main processing loop. Blocks until stop() is called.
        In production, run this in a background thread so the
        PartsCheck module can keep adding jobs concurrently.
        """
        while self._running or not self._job_queue.empty():
            try:
                job = self._job_queue.get(timeout=2)
                self._process_job(job)
                self._job_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"Unhandled error in job loop: {e}")

    # ── Job Processing ────────────────────────────────────────

    def _process_job(self, job: OfferJob):
        """
        Full pipeline for one offer:
          1. Resolve make code
          2. Look up part in ERA Power
          3. Calculate floor price
          4. Submit to PartsCheck  ← partscheck module handles this
          5. Wait for reveal        ← partscheck module handles this
          6. Compare prices
          7. Requote loop if needed
          8. Invoice if won
        """
        log.info(f"Processing job: {job.offer_id}")

        try:
            # ── Step 1: Resolve make code ──────────────────────
            job.make_code = self._resolve_make_code(job.make)
            if not job.make_code:
                job.status = "error"
                job.notes  = f"Unknown make: {job.make}"
                log.error(job.notes)
                return

            # ── Step 2: Parts inquiry ──────────────────────────
            log.info(f"[{job.offer_id}] Looking up part in ERA Power...")
            part_info = lookup_part(self._window, job.make_code, job.part_number)

            if not part_info:
                job.status = "error"
                job.notes  = f"Part not found in ERA Power: {job.part_number}"
                log.error(job.notes)
                return

            job.description    = part_info["description"]
            job.our_sell_price = part_info["sale_price"]
            job.our_list_price = part_info["list_price"]
            job.avail          = part_info["avail"] or 0

            # ── Step 3: Calculate floor price ─────────────────
            # TODO: Replace with client's actual margin rules.
            # Current placeholder: floor = cost price (list_price)
            # Real rule might be: floor = list_price * 1.05 (5% minimum margin)
            job.floor_price      = job.our_list_price
            job.submitted_price  = job.our_sell_price

            log.info(
                f"[{job.offer_id}] Price: sell=${job.our_sell_price} "
                f"list=${job.our_list_price} floor=${job.floor_price}"
            )

            # ── Step 4 & 5: PartsCheck submit + wait ──────────
            # These calls are STUBS — partscheck.py fills them in.
            # The orchestrator calls back into this pipeline once
            # competitor prices are revealed.
            job.status = "awaiting_reveal"
            log.info(
                f"[{job.offer_id}] Ready to submit ${job.submitted_price} "
                f"to PartsCheck. Handing off to PartsCheck module."
            )

            # In production: partscheck module submits price, waits,
            # then calls orchestrator.on_prices_revealed(job, competitor_prices)
            # For standalone test we simulate the reveal:
            self._simulate_reveal(job)

        except Exception as e:
            job.status = "error"
            job.notes  = str(e)
            log.error(f"Job {job.offer_id} failed: {e}")
            raise
        finally:
            job.finished_at = datetime.now().isoformat()
            with self._lock:
                self._results.append(job.__dict__.copy())
            log.info(f"Job {job.offer_id} finished — status: {job.status}")

    def on_prices_revealed(self, job: OfferJob, competitor_prices: List[float]):
        """
        Called by PartsCheck module once competitor prices are revealed.
        Runs the price comparison + requote loop.

        Args:
            job:               the OfferJob being processed
            competitor_prices: list of floats from PartsCheck reveal
        """
        job.competitor_prices = competitor_prices
        job.lowest_competitor = min(competitor_prices) if competitor_prices else 0.0

        log.info(
            f"[{job.offer_id}] Prices revealed. "
            f"Our price: ${job.submitted_price} | "
            f"Lowest competitor: ${job.lowest_competitor}"
        )

        self._run_price_decision(job)

    # ── Price Decision Loop ───────────────────────────────────

    def _run_price_decision(self, job: OfferJob):
        """
        Core logic:
          - If we're already the lowest → we won
          - If we can go lower (above floor) → requote
          - If we can't go lower → walk away
        """
        # Already won
        if job.submitted_price <= job.lowest_competitor:
            log.info(f"[{job.offer_id}] ✅ We are the lowest! We WON.")
            job.status = "won"
            self._create_winning_invoice(job)
            return

        # Can we go lower?
        new_price = self._calculate_requote_price(job)

        if new_price is None:
            log.info(f"[{job.offer_id}] ❌ Cannot go lower than floor ${job.floor_price}. Walking away.")
            job.status = "walked"
            job.notes  = f"Competitor low ${job.lowest_competitor} below our floor ${job.floor_price}"
            return

        # Check requote attempt cap
        if job.requote_attempts >= MAX_REQUOTES:
            log.info(f"[{job.offer_id}] ⚠️  Max requotes ({MAX_REQUOTES}) reached. Walking away.")
            job.status = "walked"
            job.notes  = f"Max requotes reached. Competitor low: ${job.lowest_competitor}"
            return

        # Requote
        job.requote_attempts += 1
        log.info(
            f"[{job.offer_id}] Requoting at ${new_price} "
            f"(attempt {job.requote_attempts}/{MAX_REQUOTES})..."
        )
        job.submitted_price = new_price
        job.status = "requoting"

        # If quote already exists, modify it; otherwise create fresh
        if job.quote_number:
            updated_parts = [{
                "part_number": job.part_number,
                "qty":         job.qty,
                "sale_price":  new_price,
            }]
            requote(self._window, job.quote_number, updated_parts)
        else:
            # First requote — create the quote now
            parts = [{ "part_number": job.part_number, "qty": job.qty, "sale_price": new_price }]
            q = create_quote(self._window, job.make_code, job.customer_search, parts)
            job.quote_number = q.get("quote_number")

        # Hand back to PartsCheck module to submit new price and wait again
        # In production: partscheck.py re-submits and calls on_prices_revealed() again
        # For test: simulate next reveal
        log.info(f"[{job.offer_id}] New price submitted. Waiting for next reveal...")
        self._simulate_reveal(job)

    def _calculate_requote_price(self, job: OfferJob) -> Optional[float]:
        """
        Determines the new requote price.

        Rules (placeholders — confirm with client):
          - Target: $0.50 below the lowest competitor
          - Hard floor: we never go below floor_price
          - If target < floor → return None (can't compete)

        # TODO: Replace with client's actual rules:
        #   - Fixed $ margin below competitor?
        #   - % below competitor?
        #   - Per-brand rules?
        #   - Per-category floor?
        """
        target = round(job.lowest_competitor - 0.50, 2)

        if target < job.floor_price:
            return None

        return target

    def _create_winning_invoice(self, job: OfferJob):
        """
        Creates the ERA Power quote + invoice once a win is confirmed.
        Quote is NOT created before this point.
        """
        log.info(f"[{job.offer_id}] Creating winning quote + invoice...")

        parts = [{
            "part_number": job.part_number,
            "qty":         job.qty,
            "sale_price":  job.submitted_price,
        }]

        # Create quote first
        q = create_quote(
            self._window,
            make_code=job.make_code,
            customer_search=job.customer_search,
            parts=parts,
        )
        job.quote_number = q.get("quote_number")
        log.info(f"[{job.offer_id}] Quote #{job.quote_number} created.")

        # Convert to invoice
        inv = convert_to_invoice(
            self._window,
            make_code=job.make_code,
            customer_search=job.customer_search,
            parts=parts,
        )
        job.invoice_number = inv.get("invoice_number")
        job.status = "invoiced"
        log.info(f"[{job.offer_id}] Invoice #{job.invoice_number} created. ✅")

    # ── Helpers ───────────────────────────────────────────────

    def _resolve_make_code(self, make: str) -> Optional[str]:
        """
        Converts a make name to ERA Power make code.
        e.g. "toyota" → "TO", "Mercedes-Benz" → "MB"
        """
        normalized = make.lower().strip()
        code = MAKE_CODES.get(normalized)
        if not code:
            log.warning(f"Make '{make}' not in MAKE_CODES — trying uppercase match...")
            # Try partial match
            for key, val in MAKE_CODES.items():
                if key in normalized or normalized in key:
                    code = val
                    break
        return code

    def _simulate_reveal(self, job: OfferJob):
        """
        STUB — simulates competitor price reveal for standalone testing.
        In production this is replaced by the PartsCheck module calling
        on_prices_revealed() after scraping the reveal page.

        # TODO: Remove this method once partscheck.py is integrated.
        """
        log.info(f"[{job.offer_id}] [SIMULATED] Competitor prices revealed.")

        # Hardcoded test scenario — change to test different outcomes
        simulated_competitor_prices = [22.00, 24.50, 25.00]

        self.on_prices_revealed(job, simulated_competitor_prices)

    def _save_results(self):
        """Saves all job results to JSON log file."""
        try:
            with open(RESULTS_FILE, "w") as f:
                json.dump(self._results, f, indent=2)
            log.info(f"Results saved to: {RESULTS_FILE}")
        except Exception as e:
            log.error(f"Could not save results: {e}")

    def get_results(self):
        """Returns all completed job results."""
        with self._lock:
            return list(self._results)


# ═══════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Test with hardcoded jobs.
    Simulates 2 concurrent PartsCheck offers going through the full pipeline.
    ERA Power processes them one at a time via the queue.

    Replace hardcoded values with dynamic data from PartsCheck in production.
    """

    # ── hardcoded test jobs ──────────────────────────────────
    test_jobs = [
        OfferJob(
            offer_id        = "PC-001",
            make            = "toyota",
            part_number     = "2321721010",
            qty             = 1,
            customer_search = "ABC",
        ),
        OfferJob(
            offer_id        = "PC-002",
            make            = "holden",
            part_number     = "92068768",
            qty             = 2,
            customer_search = "XYZ",
        ),
    ]

    orch = Orchestrator()

    try:
        orch.start()

        # Add all jobs to the queue
        for job in test_jobs:
            orch.add_job(job)

        # Process all jobs (blocks until done)
        orch.run_loop()

    finally:
        orch.stop()

    # Print summary
    print("\n══════ RESULTS SUMMARY ══════")
    for r in orch.get_results():
        print(
            f"  {r['offer_id']} | {r['make']} {r['part_number']} | "
            f"Status: {r['status']} | "
            f"Price: ${r['submitted_price']} | "
            f"Quote: {r['quote_number']} | Invoice: {r['invoice_number']}"
        )
    print(f"\n💾 Full log: {RESULTS_FILE}")