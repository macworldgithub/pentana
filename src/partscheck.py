"""
PartsCheck Module (Stub)
"""
import logging
from typing import Dict, List, Any

log = logging.getLogger("eraPower.partscheck")

class PartsCheckModule:
    def submit_quote(self, job) -> bool:
        """
        TODO: Implement PartsCheck quote submission
        For now returns True (simulated)
        """
        log.info(f"[{job.quote_request_id}] (STUB) Submitting quote to PartsCheck.")
        return True

    def get_competitor_prices(self, job) -> dict:
        """
        TODO: Implement competitor price scraping
        Returns dict of prices per part:
        {
          "line_item_id": [competitor_price_1, competitor_price_2]
        }
        For now returns simulated prices
        """
        log.info(f"[{job.quote_request_id}] (STUB) Fetching competitor prices.")
        simulated_prices = {}
        for item in job.parts:
            # Simulate a price slightly lower than our submitted price for testing
            if getattr(item, 'initial_quote_price', 0) > 0:
                simulated_prices[item.line_item_id] = [max(item.initial_quote_price - 1.0, 1.0)]
            else:
                simulated_prices[item.line_item_id] = [20.0, 25.0]
        return simulated_prices

    def monitor_new_requests(self) -> list:
        """
        TODO: Implement PartsCheck request monitoring
        For now returns hardcoded test requests
        """
        import datetime
        log.info("(STUB) Monitoring new PartsCheck requests.")
        return [
            {
                "partscheck_offer_id": "PC-TEST-001",
                "customer_search": "ABC Smash Repairs",
                "deadline": datetime.datetime.now() + datetime.timedelta(hours=2),
                "repairer_details": {"name": "ABC Smash Repairs", "phone": "555-1234"},
                "parts": [
                    {
                        "raw_description": "Toyota Camry brake pad",
                        "rough_part_number": "0446506200",
                        "make": "toyota",
                        "qty": 1
                    }
                ]
            }
        ]
