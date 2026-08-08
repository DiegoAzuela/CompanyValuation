#!/usr/bin/env python3
"""
Description: Assembles a cash flow statement for a given CIK, year, and period by iterating
over the concept fallback chains defined in taxonomies_and_concepts.json.

Layer responsibilities:
  data_sources/sec.py        → fetches raw concept values from EDGAR
  financial_statements/      → assembles raw values into structured statements
  valuation_models/          → consumes finished statements for DCF, multiples, etc.

Usage:
    cf = CashFlowStatement(cik="320193", year=2023, period=Period.FY).build()
    cf.summarize()

    fcf = cf.free_cash_flow()
    print(cf.is_coherent())
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Union
from financial_statements import FinancialStatement, Period

if TYPE_CHECKING:
    from financial_statements.balance_sheet import BalanceSheet
    from financial_statements.income_statement import IncomeStatement


class CashFlowStatement(FinancialStatement):

    _SECTIONS = FinancialStatement._CONCEPTS['cash_flow_statement']
    _CRITICAL = {
        'operating_activities': 'operating_cf',
        'investing_activities': 'investing_cf',
        'financing_activities': 'financing_cf',
    }

    def __init__(self, cik: str, year: int, period: Union[Period, str] = Period.FY):
        super().__init__(cik, year, period)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_line_item(self, section: str, line: str) -> Optional[float]:
        return self.data.get(section, {}).get(line, {}).get('val')

    def get_operating_cf(self) -> Optional[float]:
        return self.get_line_item('operating_activities', 'operating_cf')

    def get_investing_cf(self) -> Optional[float]:
        return self.get_line_item('investing_activities', 'investing_cf')

    def get_financing_cf(self) -> Optional[float]:
        return self.get_line_item('financing_activities', 'financing_cf')

    def get_capex(self) -> Optional[float]:
        return self.get_line_item('investing_activities', 'capex')

    def get_dividends_paid(self) -> Optional[float]:
        return self.get_line_item('financing_activities', 'dividends_paid')

    def get_net_change_in_cash(self) -> Optional[float]:
        return self.get_line_item('cash_summary', 'net_change_in_cash')

    def get_ending_cash(self) -> Optional[float]:
        return self.get_line_item('cash_summary', 'ending_cash')
    
    def get_share_repurchased(self) -> Optional[float]:
        return self.get_line_item('financing_activities', 'share_repurchases')

    def get_sbc(self) -> Optional[float]:
        return self.get_line_item('operating_activities', 'stock_based_compensation')

    def get_proceeds_from_stock_issuance(self) -> Optional[float]:
        return self.get_line_item('financing_activities', 'proceeds_from_stock_issuance')

    # ------------------------------------------------------------------
    # Derived metrics
    # ------------------------------------------------------------------

    def free_cash_flow(self) -> Optional[float]:
        """Operating CF minus capex — primary input for DCF valuation."""
        op_cf = self.get_operating_cf()
        capex = self.get_capex()
        if op_cf is None or capex is None:
            return None
        return op_cf - abs(capex)  # capex is filed as negative in EDGAR

    def operating_cf_to_net_income(self, income_stmt: 'IncomeStatement') -> Optional[float]:
        """
        Earnings quality ratio: operating CF / net income.
        Ratio persistently below 1.0 means earnings aren't converting to cash —
        a red flag for aggressive accrual accounting.
        Requires a built IncomeStatement for the same period.
        """
        op_cf = self.get_operating_cf()
        ni    = income_stmt.get_net_income()
        if op_cf is None or not ni:
            return None
        return op_cf / ni

    # ------------------------------------------------------------------
    # Validation — single period
    # ------------------------------------------------------------------

    def is_coherent(self, tolerance: float = 1.0) -> dict:
        """
        Checks that net change in cash reconciles with the three activity totals.
        Returns per-tier bool, or None if data is insufficient.
        """
        op_cf   = self.get_operating_cf()
        inv_cf  = self.get_investing_cf()
        fin_cf  = self.get_financing_cf()
        net_chg = self.get_net_change_in_cash()

        results = {}

        if all(v is not None for v in [op_cf, inv_cf, fin_cf, net_chg]):
            results['net_change_in_cash'] = abs(net_chg - (op_cf + inv_cf + fin_cf)) <= tolerance
        else:
            results['net_change_in_cash'] = None

        return results

    # ------------------------------------------------------------------
    # Validation — cross-statement (requires BalanceSheet)
    # ------------------------------------------------------------------

    def ending_cash_check(self, bs: 'BalanceSheet', tolerance: float = 1.0) -> Optional[bool]:
        """
        Ending cash on the cash flow statement should match cash_and_equivalents
        on the balance sheet for the same period.
        """
        ending_cash = self.get_ending_cash()
        bs_cash     = bs.get_cash()
        if ending_cash is None or bs_cash is None:
            return None
        return abs(ending_cash - bs_cash) <= tolerance

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summarize(self) -> None:
        if not self.data:
            print("No data — call build() first.")
            return

        meta = self.data.get('meta', {})
        print(f"\n{'='*60}")
        print(f"Cash Flow Statement — CIK {meta.get('cik')}  |  {meta.get('frame')}")
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

        print(f"\n  {'─'*50}")
        print(f"  Derived Metrics")
        print(f"  {'─'*50}")
        fcf = self.free_cash_flow()
        print(f"       {'Free Cash Flow':<45} {'$' + f'{fcf:>20,.0f}':>21}" if fcf is not None else f"       {'Free Cash Flow':<45} {'N/A':>21}")

        missing = meta.get('missing_line_items', [])
        if missing:
            print(f"\n  ⚠  {len(missing)} line item(s) not found for this CIK:")
            for m in missing:
                print(f"       - [{m['section']}] {m['label']}")
                print(f"         Tried: {', '.join(m['candidates_tried'])}")

        coherence = self.is_coherent()
        nc_ok = coherence.get('net_change_in_cash')
        print(f"\n  {'─'*50}")
        print(f"  Coherence Checks  (cross-statement checks require calling directly)")
        print(f"  {'─'*50}")
        print(f"       {'Net change in cash arithmetic':<45} {'✓ PASS' if nc_ok else ('✗ FAIL' if nc_ok is False else 'N/A'):>21}")
        print(f"{'='*60}\n")

    def __repr__(self) -> str:
        status = self.data.get('meta', {}).get('status', 'not built') if self.data else 'not built'
        return f"CashFlowStatement(cik={self.cik}, year={self.year}, period={self.period.value}, status={status})"
