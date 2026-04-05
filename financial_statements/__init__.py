#!/usr/bin/env python3
"""
Description: Base class for all financial statements
"""


import json
import os
from enum import Enum
from typing import Optional

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

    def __init__(self, cik: str, year: int, period: Period | str):
        self.cik    = cik
        self.year   = year
        self.period = Period(period.upper()) if isinstance(period, str) else period
        self.data:  dict = {}

    # ------------------------------------------------------------------
    # Frame string — overridden by each subclass
    # ------------------------------------------------------------------

    def _build_frame_string(self) -> str:
        """
        Builds the SEC frame string for this statement type and period.
        Must be overridden by subclasses since balance sheets use instant
        frames (ending in 'I') and income statements use duration frames.
        """
        raise NotImplementedError("Subclasses must implement _build_frame_string()")

    # ------------------------------------------------------------------
    # Core fallback resolver — shared by all subclasses
    # ------------------------------------------------------------------

    def _resolve_concept(
        self,
        candidates: list[str],
        line_type: str = 'monetary'
    ) -> tuple[Optional[str], Optional[float]]:
        """
        Tries each candidate XBRL tag in order and returns the first match
        found for this instance's CIK, frame, and unit.

        The unit is derived from the line item's type field in the JSON:
            monetary  → USD          (default — balance sheet and P&L amounts)
            perShare  → USD/shares   (EPS concepts)
            shares    → shares       (weighted average share counts)

        Args:
            candidates: Ordered list of XBRL tags to try, from taxonomies_and_concepts.json
            line_type:  Type field from the concept map entry — 'monetary', 'perShare', 'shares'

        Returns:
            (matched_tag, value) — or (None, None) if no candidate matched.
        """
        unit_map = {
            'monetary': 'USD',
            'perShare': 'USD/shares',
            'shares':   'shares'
        }
        unit      = unit_map.get(line_type, 'USD')
        frame_str = self._build_frame_string()

        for tag in candidates:
            result = SecData.get_concept_frameAndCik(
                cik=self.cik,
                taxonomy=self._TAXONOMY,
                concept=tag,
                frame=frame_str,
                unit=unit
            )
            if result and result.get('val') is not None:
                return tag, result['val']

        return None, None

    def __repr__(self) -> str:
        status = self.data.get('meta', {}).get('status', 'not built') if self.data else 'not built'
        return (
            f"{self.__class__.__name__}("
            f"cik={self.cik}, "
            f"year={self.year}, "
            f"period={self.period.value}, "
            f"status={status})"
        )