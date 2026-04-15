#!/usr/bin/env python3
"""
Description: Base class for all financial statements
"""


import json
import os

from enum import Enum
from typing import Union, Optional

from data_sources.sec import SecData


class Period(str, Enum):
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"   # year-end balance sheet — equivalent to FY for a snapshot
    FY = "FY"   # full-year duration — income statement only; maps to Q4I for balance sheet


class FinancialStatement:
    """
    Base class for all financial statements.

    Responsibilities:
      - Loads taxonomies_and_concepts.json once, shared across all subclasses
      - Provides the Period enum and frame string builder used by all statements
      - Provides the core concept fallback resolver used by all statements

    Subclasses:
      - BalanceSheet  → uses instant frames (CY{year}Q{n}I)
      - IncomeStatement → uses duration frames (CY{year}Q{n} or CY{year})
    """

    _CONCEPTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'storage', 'taxonomies_and_concepts.json')
    
    with open(_CONCEPTS_PATH, 'r') as _f:
        _CONCEPTS: dict = json.load(_f)

    _TAXONOMY: str = _CONCEPTS['_meta']['taxonomy']  # "us-gaap"

    # ------------------------------------------------------------------
    # Subclasses must define which section of _CONCEPTS they own
    # ------------------------------------------------------------------

    _SECTIONS: dict = {}  # overridden by BalanceSheet and IncomeStatement

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, cik: str, year: int, period: Union[Period, str] = Period.Q4):
        self.cik          = cik
        self.year         = year
        self.period       = Period(period.upper()) if isinstance(period, str) else period
        self.data:  dict  = {}
        self._target_date: Optional[str] = None  # cached after first call

    # ------------------------------------------------------------------
    # Core fallback resolver — shared by all subclasses
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        status = self.data.get('meta', {}).get('status', 'not built') if self.data else 'not built'
        return (
            f"{self.__class__.__name__}("
            f"cik={self.cik}, "
            f"year={self.year}, "
            f"period={self.period.value}, "
            f"status={status})"
        )
        
    def _get_target_date(self) -> str:
        """
        Infers the fiscal year end date by finding the most recent 10-K
        filing for this CIK that ends within the target calendar year.
        Handles non-calendar fiscal years (e.g. Apple FY ends Sept 30).
        Result is cached so the network call only happens once per build.
        """
        if self._target_date is not None:
            return self._target_date

        period_key = 'Q4' if self.period == Period.FY else self.period.value

        if period_key != 'Q4':
            quarter_end = {
                'Q1': f"{self.year}-03-31",
                'Q2': f"{self.year}-06-30",
                'Q3': f"{self.year}-09-30",
            }
            self._target_date = quarter_end[period_key]
            return self._target_date

        data = SecData.get_concept(
            cik=self.cik,
            taxonomy=self._TAXONOMY,
            concept='Assets'
        )
        units = data.get('units', {}).get('USD', [])
        annual_filings = [
            e for e in units
            if e.get('form') == '10-K'
            and e.get('end', '').startswith(str(self.year))
        ]
        if annual_filings:
            annual_filings.sort(key=lambda e: e.get('filed', ''), reverse=True)
            self._target_date = annual_filings[0]['end']
        else:
            self._target_date = f"{self.year}-12-31"

        return self._target_date


    # ------------------------------------------------------------------
    # Frame + concept resolution
    # ------------------------------------------------------------------
    def _resolve_concept(self, candidates: list[str]) -> tuple[Optional[str], Optional[float]]:
        """
        Tries each candidate XBRL tag in order via the company concept
        endpoint and returns the first match for this CIK and target date.

        Returns:
            (matched_tag, value) — or (None, None) if no candidate matched.
        """
        for tag in candidates:
            val = self._resolve_from_company_concept(tag)
            if val is not None:
                return tag, val
        return None, None

    def _resolve_from_company_concept(self, concept: str) -> Optional[float]:
        """
        Fetches the full company concept history and finds the value
        whose period-end matches the target date for this instance.
        """
        data = SecData.get_concept(
            cik=self.cik,
            taxonomy=self._TAXONOMY,
            concept=concept
        )
        if not data:
            return None

        units = data.get('units', {}).get('USD', [])
        if not units:
            return None

        target_date = self._get_target_date()

        matches = [
            e for e in units
            if e.get('end') == target_date
            and e.get('form') in ('10-K', '10-Q', '10-K/A', '10-Q/A')  # include amendments
        ]
        if not matches:
            return None

        matches.sort(key=lambda e: e.get('filed', ''), reverse=True)
        return matches[0].get('val')