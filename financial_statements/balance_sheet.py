#!/usr/bin/env python3
"""
Description: Assembles a balance sheet for a given CIK, year, and period by iterating
over the concept fallback chains defined in taxonomies_and_concepts.json.

Layer responsibilities:
  data_sources/sec.py        → fetches raw concept values from EDGAR
  financial_statements/      → assembles raw values into structured statements
  valuation_models/          → consumes finished statements for DCF, multiples, etc.

Usage:
    bs = BalanceSheet(cik="320193", year=2023, period=Period.FY).build()
    bs.summarize()

    total_assets = bs.get_total_assets()
    print(bs.is_balanced())
"""

import json
import os
from enum import Enum
from typing import Optional, Union

from data_sources.sec import SecData
from financial_statements import FinancialStatement



# financial_statements/balance_sheet.py

from financial_statements import FinancialStatement, Period


class BalanceSheet(FinancialStatement):

    _SECTIONS = FinancialStatement._CONCEPTS['balance_sheet']

    def __init__(self, cik: str, year: int, period: Period | str = Period.Q4):
        super().__init__(cik, year, period)

    def _build_frame_string(self) -> str:
        """
        Balance sheets are always point-in-time (instant), frames end in 'I'.
        FY is a convenience alias for Q4 — there is no CY{year}I in the API.

            Q1 → CY{year}Q1I
            Q2 → CY{year}Q2I
            Q3 → CY{year}Q3I
            Q4 → CY{year}Q4I
            FY → CY{year}Q4I
        """
        quarter = "Q4" if self.period == Period.FY else self.period.value
        return f"CY{self.year}{quarter}I"

    def _resolve_concept(self, candidates: list[str]) -> tuple[Optional[str], Optional[float]]:
        """
        Tries each candidate XBRL tag in order and returns the first match
        found for this instance's CIK and frame.

        Returns:
            (matched_tag, value) — or (None, None) if no candidate matched.
        """
        frame_str = self._build_frame_string()
        for tag in candidates:
            result = SecData.get_concept_frameAndCik(
                cik=self.cik,
                taxonomy=self._TAXONOMY,
                concept=tag,
                frame=frame_str
            )
            if result and result.get('val') is not None:
                return tag, result['val']
        return None, None

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> "BalanceSheet":
        """
        Iterates over every section and line item in the concept map,
        resolves values via fallback chains, and populates self.data.

        Returns self to allow chaining:
            bs = BalanceSheet("320193", 2023, Period.FY).build()
        """
        self.data = {
            "meta": {
                "cik":                self.cik,
                "year":               self.year,
                "period":             self.period.value,
                "frame":              self._build_frame_string(),
                "status":             "ok",
                "missing_line_items": []
            }
        }

        for section_key, section in self._SECTIONS.items():
            if section_key.startswith('_'):
                continue

            self.data[section_key] = {}

            for line_key, line in section.items():
                if line_key.startswith('_'):
                    continue

                candidates    = line.get('candidates', [])
                tag_used, val = self._resolve_concept(candidates)

                if val is None:
                    self.data['meta']['missing_line_items'].append({
                        'section':          section_key,
                        'line':             line_key,
                        'label':            line.get('label'),
                        'candidates_tried': candidates
                    })

                self.data[section_key][line_key] = {
                    'label':       line.get('label'),
                    'tag_used':    tag_used,
                    'val':         val,
                    'unit':        'USD',
                    'balance':     line.get('balance'),
                    'is_total':    line.get('is_total', False),
                    'is_subtotal': line.get('is_subtotal', False)
                }

        if self.data['meta']['missing_line_items']:
            self.data['meta']['status'] = 'partial'

        return self

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_line_item(self, section: str, line: str) -> Optional[float]:
        """Returns the value for any line item by section and line key."""
        return self.data.get(section, {}).get(line, {}).get('val')

    def get_total_assets(self) -> Optional[float]:
        return self.get_line_item('noncurrent_assets', 'total_assets')

    def get_total_liabilities(self) -> Optional[float]:
        return self.get_line_item('noncurrent_liabilities', 'total_liabilities')

    def get_total_equity(self) -> Optional[float]:
        return self.get_line_item('stockholders_equity', 'total_stockholders_equity')

    def get_current_assets(self) -> Optional[float]:
        return self.get_line_item('current_assets', 'total_current_assets')

    def get_current_liabilities(self) -> Optional[float]:
        return self.get_line_item('current_liabilities', 'total_current_liabilities')

    # ------------------------------------------------------------------
    # Validation & derived metrics
    # ------------------------------------------------------------------

    def is_balanced(self, tolerance: float = 1.0) -> bool:
        """
        Verifies Assets = Liabilities + Equity within a rounding tolerance.
        Tolerance is in USD — default $1 accounts for rounding in SEC filings.
        Returns False if any of the three totals are missing.
        """
        assets      = self.get_total_assets()
        liabilities = self.get_total_liabilities()
        equity      = self.get_total_equity()

        if any(v is None for v in [assets, liabilities, equity]):
            return False

        return abs(assets - (liabilities + equity)) <= tolerance

    def current_ratio(self) -> Optional[float]:
        """Current Assets / Current Liabilities — basic liquidity check."""
        ca = self.get_current_assets()
        cl = self.get_current_liabilities()
        if ca and cl:
            return ca / cl
        return None

    def debt_to_equity(self) -> Optional[float]:
        """Total Liabilities / Total Equity — leverage ratio."""
        liabilities = self.get_total_liabilities()
        equity      = self.get_total_equity()
        if liabilities and equity:
            return liabilities / equity
        return None

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summarize(self) -> None:
        """Prints a human-readable summary of the balance sheet to stdout."""
        if not self.data:
            print("No data — call build() first.")
            return

        meta = self.data.get('meta', {})
        print(f"\n{'='*60}")
        print(f"Balance Sheet — CIK {meta.get('cik')}  |  {meta.get('frame')}")
        print(f"Status: {meta.get('status').upper()}")
        print(f"{'='*60}")

        for section_key, section in self.data.items():
            if section_key == 'meta':
                continue

            section_label = self._SECTIONS.get(section_key, {}).get('_label', section_key)
            print(f"\n  {section_label}")
            print(f"  {'-'*50}")

            for line_key, line in section.items():
                val      = line.get('val')
                label    = line.get('label', line_key)
                tag      = line.get('tag_used', 'N/A')
                is_total = line.get('is_total') or line.get('is_subtotal')

                val_str = f"${val:>20,.0f}" if val is not None else f"{'N/A':>21}"
                prefix  = "  >>  " if is_total else "       "
                print(f"{prefix}{label:<45} {val_str}   [{tag}]")

        # Derived metrics
        print(f"\n  {'─'*50}")
        print(f"  Derived Metrics")
        print(f"  {'─'*50}")
        cr  = self.current_ratio()
        dte = self.debt_to_equity()
        print(f"       {'Current Ratio':<45} {f'{cr:.2f}x':>21}" if cr  else f"       {'Current Ratio':<45} {'N/A':>21}")
        print(f"       {'Debt-to-Equity':<45} {f'{dte:.2f}x':>21}" if dte else f"       {'Debt-to-Equity':<45} {'N/A':>21}")

        missing = meta.get('missing_line_items', [])
        if missing:
            print(f"\n  ⚠  {len(missing)} line item(s) not found for this CIK:")
            for m in missing:
                print(f"       - [{m['section']}] {m['label']}")
                print(f"         Tried: {', '.join(m['candidates_tried'])}")

        print(f"\n  Balanced check: {'✓ PASS' if self.is_balanced() else '✗ FAIL (or incomplete)'}")
        print(f"{'='*60}\n")

    def __repr__(self) -> str:
        status = self.data.get('meta', {}).get('status', 'not built') if self.data else 'not built'
        return f"BalanceSheet(cik={self.cik}, year={self.year}, period={self.period.value}, status={status})"