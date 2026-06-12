"""
Parts Finder Module (Stub)
"""
import logging

log = logging.getLogger("eraPower.partsfinder")

class PartsFinderModule:
    def find_part(self, raw_description: str, rough_part_number: str, make: str) -> dict:
        """
        TODO: Implement parts catalogue lookup once catalogue confirmed
        
        Returns:
        {
          "confirmed_part_number": str,
          "confirmed_make_code": str,
          "alternatives": list,
          "found": bool
        }
        
        For now: returns rough_part_number as confirmed (passthrough)
        """
        log.info(f"(STUB) Looking up part: {raw_description}")
        return {
            "confirmed_part_number": rough_part_number,
            "confirmed_make_code": "", # Orchestrator will resolve make code
            "alternatives": [],
            "found": True
        }
