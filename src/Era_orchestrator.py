"""
ERA Power Orchestrator
Controls the workflow between ERA Power, PartsCheck, and Parts Finder.
"""
import time
import json
import uuid
import queue
import logging
import threading
import traceback
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from Era_power import launch_era_port, login, logoff_era, lookup_part, MAKE_CODES
from Era_customer import lookup_customer
from Era_quote import create_quote, create_sales_order
from partscheck import PartsCheckModule
from parts_finder import PartsFinderModule

log = logging.getLogger("eraPower.orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load Config
CONFIG_FILE = r"C:\Projects\pentana\era_config.json"
try:
    with open(CONFIG_FILE, "r") as f:
        CONFIG = json.load(f)
except Exception as e:
    log.warning(f"Failed to load config from {CONFIG_FILE}: {e}")
    CONFIG = {}

# Constants from config
PATHS = CONFIG.get("paths", {})
RESULTS_LOG = PATHS.get("results_log", r"C:\Projects\pentana\era_results_log.json")
ERROR_LOG = PATHS.get("error_log", r"C:\Projects\pentana\era_errors.json")
DLQ_FILE = PATHS.get("dead_letter_queue", r"C:\Projects\pentana\dead_letter_queue.json")

# Ensure directory exists for logs
os.makedirs(os.path.dirname(RESULTS_LOG), exist_ok=True)

MARGIN_RULES = CONFIG.get("margin_rules", {})
REQUOTE_RULES = CONFIG.get("requote_rules", {})

MAX_REQUOTE_ATTEMPTS = REQUOTE_RULES.get("max_requote_attempts", 3)
UNDERCUT_FIXED = REQUOTE_RULES.get("undercut_fixed_amount", 0.50)
MIN_IMPROVEMENT = REQUOTE_RULES.get("min_improvement_threshold", 1.00)

class RequestStatus:
    PENDING = "PENDING"
    CUSTOMER_LOOKING_UP = "CUSTOMER_LOOKING_UP"
    CUSTOMER_FOUND = "CUSTOMER_FOUND"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    PARTS_PROCESSING = "PARTS_PROCESSING"
    QUOTE_CREATING = "QUOTE_CREATING"
    QUOTE_CREATED = "QUOTE_CREATED"
    FIRST_QUOTE_SUBMITTED = "FIRST_QUOTE_SUBMITTED"
    WAITING_COMPETITOR_PRICES = "WAITING_COMPETITOR_PRICES"
    COMPETITOR_PRICES_CAPTURED = "COMPETITOR_PRICES_CAPTURED"
    REQUOTE_CALCULATING = "REQUOTE_CALCULATING"
    REQUOTE_SUBMITTED = "REQUOTE_SUBMITTED"
    WON = "WON"
    LOST = "LOST"
    WALKED = "WALKED"
    INVOICED = "INVOICED"
    ERROR = "ERROR"

class LineItemStatus:
    PENDING = "PENDING"
    MAKE_RESOLVING = "MAKE_RESOLVING"
    MAKE_RESOLVED = "MAKE_RESOLVED"
    MAKE_NOT_FOUND = "MAKE_NOT_FOUND"
    ERA_LOOKING_UP = "ERA_LOOKING_UP"
    ERA_FOUND = "ERA_FOUND"
    ERA_NOT_FOUND = "ERA_NOT_FOUND"
    PRICE_CALCULATING = "PRICE_CALCULATING"
    PRICE_READY = "PRICE_READY"
    CANNOT_COMPETE = "CANNOT_COMPETE"
    REQUOTED = "REQUOTED"
    NO_ACTION_NEEDED = "NO_ACTION_NEEDED"

@dataclass
class LineItem:
    line_item_id: str
    raw_description: str
    rough_part_number: str
    make: str
    qty: int
    
    status: str = LineItemStatus.PENDING
    make_code: Optional[str] = None
    confirmed_part_number: Optional[str] = None
    
    # ERA Power data
    era_description: str = ""
    era_sale_price: float = 0.0
    era_list_price: float = 0.0
    era_avail: int = 0
    
    # Calculated
    floor_price: float = 0.0
    initial_quote_price: float = 0.0
    current_quote_price: float = 0.0
    
    competitor_prices: List[float] = field(default_factory=list)

@dataclass
class Job:
    quote_request_id: str
    partscheck_offer_id: str
    customer_search: str
    deadline: datetime
    repairer_details: dict
    parts: List[LineItem] = field(default_factory=list)
    
    status: str = RequestStatus.PENDING
    customer_entity_id: Optional[str] = None
    quote_number: Optional[str] = None
    invoice_number: Optional[str] = None
    requote_attempts: int = 0
    
    history: List[str] = field(default_factory=list)

class Orchestrator:
    def __init__(self):
        self._window = None
        self._job_queue = queue.Queue()
        self._running = False
        self._lock = threading.Lock()
        
        self.partscheck = PartsCheckModule()
        self.partsfinder = PartsFinderModule()

    def _log_action(self, job: Job, item: Optional[LineItem], action: str, result: str, prices: str, reason: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item_str = f"[{item.line_item_id}]" if item else "[]"
        log_msg = f"{timestamp} [INFO] [{job.quote_request_id}] {item_str} {action}: result={result} prices={prices} reason={reason}"
        log.info(log_msg)
        job.history.append(log_msg)
        self._save_results(job)

    def _save_results(self, job: Job):
        try:
            results = []
            if os.path.exists(RESULTS_LOG):
                with open(RESULTS_LOG, "r") as f:
                    results = json.load(f)
            
            # Simple update or append
            for i, r in enumerate(results):
                if r.get("quote_request_id") == job.quote_request_id:
                    results[i] = self._job_to_dict(job)
                    break
            else:
                results.append(self._job_to_dict(job))
                
            with open(RESULTS_LOG, "w") as f:
                json.dump(results, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save results log: {e}")

    def _send_to_dlq(self, job: Job, error_msg: str):
        try:
            dlq = []
            if os.path.exists(DLQ_FILE):
                with open(DLQ_FILE, "r") as f:
                    dlq = json.load(f)
            job_dict = self._job_to_dict(job)
            job_dict["error"] = error_msg
            dlq.append(job_dict)
            with open(DLQ_FILE, "w") as f:
                json.dump(dlq, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to write to DLQ: {e}")

    def _job_to_dict(self, job: Job) -> dict:
        import copy
        j_dict = copy.deepcopy(job.__dict__)
        j_dict["parts"] = [p.__dict__ for p in job.parts]
        return j_dict

    def generate_ids(self, raw_job: dict) -> Job:
        date_str = datetime.now().strftime("%Y%m%d")
        uuid_str = str(uuid.uuid4())[:8]
        req_id = f"QR-{date_str}-{uuid_str}"
        
        job = Job(
            quote_request_id=req_id,
            partscheck_offer_id=raw_job.get("partscheck_offer_id", ""),
            customer_search=raw_job.get("customer_search", ""),
            deadline=raw_job.get("deadline", datetime.now()),
            repairer_details=raw_job.get("repairer_details", {})
        )
        
        for idx, part_data in enumerate(raw_job.get("parts", []), start=1):
            line_item_id = f"{req_id}-LI-{idx:02d}"
            item = LineItem(
                line_item_id=line_item_id,
                raw_description=part_data.get("raw_description", ""),
                rough_part_number=part_data.get("rough_part_number", ""),
                make=part_data.get("make", ""),
                qty=part_data.get("qty", 1)
            )
            job.parts.append(item)
            
        return job

    def add_job(self, raw_job: dict):
        job = self.generate_ids(raw_job)
        self._log_action(job, None, "Job Created", "SUCCESS", "", "Incoming request")
        self._job_queue.put(job)

    def _retry_call(self, func, *args, **kwargs):
        """Retries an ERA Power function call with exponential backoff (2s, 4s, 8s)."""
        delays = [2, 4, 8]
        for attempt in range(4):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < 3:
                    log.warning(f"Call failed: {e}. Retrying in {delays[attempt]}s...")
                    time.sleep(delays[attempt])
                else:
                    log.error(f"Call failed after 3 retries: {e}")
                    raise

    def process_job(self, job: Job):
        try:
            self._process_steps(job)
        except Exception as e:
            job.status = RequestStatus.ERROR
            error_msg = f"Job failed: {str(e)}\n{traceback.format_exc()}"
            self._log_action(job, None, "Job Error", "ERROR", "", error_msg)
            self._send_to_dlq(job, error_msg)

    def _process_steps(self, job: Job):
        # STEP 1: Customer Lookup
        job.status = RequestStatus.CUSTOMER_LOOKING_UP
        self._log_action(job, None, "Customer Lookup", "STARTED", "", job.customer_search)
        
        cust_result = self._retry_call(lookup_customer, self._window, job.customer_search)
        if not cust_result:
            job.status = RequestStatus.CUSTOMER_NOT_FOUND
            self._log_action(job, None, "Customer Lookup", "FAILED", "", "Not found in ERA")
            raise Exception("Customer not found in ERA Power")
            
        if isinstance(cust_result, list):
            cust_result = cust_result[0] # Take first result as per requirements
            
        job.customer_entity_id = cust_result.get("entity_id") or cust_result.get("customer_number")
        
        job.status = RequestStatus.CUSTOMER_FOUND
        self._log_action(job, None, "Customer Lookup", "SUCCESS", "", f"ID: {job.customer_entity_id}")

        # STEP 2: Parts Lookup
        job.status = RequestStatus.PARTS_PROCESSING
        valid_parts = []
        for item in job.parts:
            # 2a) Resolve make
            item.status = LineItemStatus.MAKE_RESOLVING
            make_normalized = item.make.lower().strip()
            make_code = MAKE_CODES.get(make_normalized)
            if not make_code:
                for k, v in MAKE_CODES.items():
                    if k in make_normalized or make_normalized in k:
                        make_code = v
                        break
                        
            if not make_code:
                item.status = LineItemStatus.MAKE_NOT_FOUND
                self._log_action(job, item, "Resolve Make", "FAILED", "", f"Make: {item.make}")
                continue
                
            item.make_code = make_code
            item.status = LineItemStatus.MAKE_RESOLVED
            
            # Parts Finder Lookup
            pf_result = self.partsfinder.find_part(item.raw_description, item.rough_part_number, item.make)
            item.confirmed_part_number = pf_result.get("confirmed_part_number", item.rough_part_number)
            
            # 2b) ERA Lookup
            item.status = LineItemStatus.ERA_LOOKING_UP
            part_info = self._retry_call(lookup_part, self._window, item.make_code, item.confirmed_part_number)
            
            if not part_info:
                item.status = LineItemStatus.ERA_NOT_FOUND
                self._log_action(job, item, "ERA Lookup", "FAILED", "", f"Part: {item.confirmed_part_number}")
                continue
                
            item.era_description = part_info.get("description", "")
            item.era_sale_price = part_info.get("sale_price", 0.0)
            item.era_list_price = part_info.get("list_price", 0.0)
            item.era_avail = part_info.get("avail", 0)
            item.status = LineItemStatus.ERA_FOUND
            self._log_action(job, item, "ERA Lookup", "SUCCESS", f"sale={item.era_sale_price} list={item.era_list_price}", f"avail={item.era_avail}")
            valid_parts.append(item)

        if not valid_parts:
            job.status = RequestStatus.ERROR
            raise Exception("No valid parts found in ERA Power")

        # STEP 3: Price Calculation
        for item in valid_parts:
            item.status = LineItemStatus.PRICE_CALCULATING
            
            brand_margin = MARGIN_RULES.get("by_brand", {}).get(item.make_code, MARGIN_RULES.get("by_brand", {}).get("default", 0.10))
            cat_margin = MARGIN_RULES.get("by_category", {}).get("default", 0.15) 
            
            margin = max(brand_margin, cat_margin)
            item.floor_price = item.era_list_price + (item.era_list_price * margin)
            item.initial_quote_price = item.era_sale_price
            item.current_quote_price = item.initial_quote_price
            
            item.status = LineItemStatus.PRICE_READY
            self._log_action(job, item, "Price Calc", "SUCCESS", f"floor={item.floor_price:.2f} quote={item.initial_quote_price:.2f}", f"margin={margin}")

        # STEP 4: Create Quote in ERA Power
        job.status = RequestStatus.QUOTE_CREATING
        era_parts_list = [
            {"part_number": item.confirmed_part_number, "qty": item.qty, "sale_price": item.current_quote_price}
            for item in valid_parts
        ]
        make_code = valid_parts[0].make_code
        
        quote_result = self._retry_call(create_quote, self._window, make_code, str(job.customer_entity_id), era_parts_list)
        if quote_result and quote_result.get("quote_number"):
            job.quote_number = quote_result.get("quote_number")
            job.status = RequestStatus.QUOTE_CREATED
            self._log_action(job, None, "ERA Quote", "SUCCESS", "", f"Quote# {job.quote_number}")
        else:
            raise Exception("Quote creation failed")

        # STEP 5: Hand off to PartsCheck
        self.partscheck.submit_quote(job)
        job.status = RequestStatus.FIRST_QUOTE_SUBMITTED
        self._log_action(job, None, "PartsCheck Submit", "SUCCESS", "", "Initial quote submitted")

        # STEP 6: Wait for competitor prices
        job.status = RequestStatus.WAITING_COMPETITOR_PRICES
        
        time.sleep(2)
        comp_prices = self.partscheck.get_competitor_prices(job)
        if comp_prices:
            for item in valid_parts:
                item.competitor_prices = comp_prices.get(item.line_item_id, [])
            job.status = RequestStatus.COMPETITOR_PRICES_CAPTURED
            self._log_action(job, None, "Competitor Prices", "SUCCESS", "", f"Received for {len(comp_prices)} items")
            self._requote_decision(job, valid_parts, make_code)
        else:
            self._log_action(job, None, "Competitor Prices", "EMPTY", "", "No competitor prices found")
            self._win_loss_handling(job, valid_parts, make_code)


    def _requote_decision(self, job: Job, valid_parts: List[LineItem], make_code: str):
        job.status = RequestStatus.REQUOTE_CALCULATING
        any_improved = False
        
        for item in valid_parts:
            if not item.competitor_prices:
                item.status = LineItemStatus.NO_ACTION_NEEDED
                continue
                
            lowest_comp = min(item.competitor_prices)
            if item.current_quote_price <= lowest_comp:
                item.status = LineItemStatus.NO_ACTION_NEEDED
                self._log_action(job, item, "Requote Calc", "SKIP", f"ours={item.current_quote_price} comp={lowest_comp}", "Already lowest")
                continue
                
            target_price = lowest_comp - UNDERCUT_FIXED
            
            if target_price < item.floor_price:
                item.status = LineItemStatus.CANNOT_COMPETE
                self._log_action(job, item, "Requote Calc", "SKIP", f"target={target_price} floor={item.floor_price}", "Below floor")
                continue
                
            if (item.current_quote_price - target_price) < MIN_IMPROVEMENT:
                item.status = LineItemStatus.CANNOT_COMPETE
                self._log_action(job, item, "Requote Calc", "SKIP", f"diff={item.current_quote_price - target_price}", "Below min improvement")
                continue
                
            item.current_quote_price = target_price
            item.status = LineItemStatus.REQUOTED
            any_improved = True
            self._log_action(job, item, "Requote Calc", "SUCCESS", f"new_price={item.current_quote_price}", "Beats competitor")

        if any_improved:
            self.partscheck.submit_quote(job)
            job.status = RequestStatus.REQUOTE_SUBMITTED
            self._log_action(job, None, "Requote Submit", "SUCCESS", "", "Updated quote submitted to PartsCheck")
        else:
            job.status = RequestStatus.WALKED
            self._log_action(job, None, "Requote Decision", "WALKED", "", "No parts could be competitively improved")
            
        self._win_loss_handling(job, valid_parts, make_code)

    def _win_loss_handling(self, job: Job, valid_parts: List[LineItem], make_code: str):
        is_won = True # STUB
        
        if is_won:
            job.status = RequestStatus.WON
            era_parts_list = [
                {"part_number": item.confirmed_part_number, "qty": item.qty, "sale_price": item.current_quote_price}
                for item in valid_parts
            ]
            
            so_result = self._retry_call(create_sales_order, self._window, make_code, str(job.customer_entity_id), era_parts_list)
            if so_result and so_result.get("invoice_number"):
                job.invoice_number = so_result.get("invoice_number")
                job.status = RequestStatus.INVOICED
                self._log_action(job, None, "Sales Order", "SUCCESS", "", f"Invoice# {job.invoice_number}")
            else:
                self._log_action(job, None, "Sales Order", "FAILED", "", "Invoice creation failed")
        else:
            job.status = RequestStatus.LOST
            self._log_action(job, None, "Outcome", "LOST", "", "Lost quote")

    def run(self):
        log.info("Starting Orchestrator...")
        self._window = launch_era_port()
        login(self._window)
        self._running = True
        
        while self._running or not self._job_queue.empty():
            try:
                job = self._job_queue.get(timeout=2)
                self.process_job(job)
                self._job_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"Queue loop error: {e}")

    def stop(self):
        self._running = False
        if self._window:
            self._window = logoff_era(self._window)
        log.info("Orchestrator stopped.")

if __name__ == "__main__":
    orch = Orchestrator()
    pc_module = PartsCheckModule()
    
    for req in pc_module.monitor_new_requests():
        orch.add_job(req)
        
    threading.Thread(target=orch.run).start()
    time.sleep(15)
    orch.stop()