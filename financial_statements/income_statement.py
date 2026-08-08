#!/usr/bin/env python3
"""
Description: Assembles an income statement for a given CIK, year, and period by iterating
over the concept fallback chains defined in taxonomies_and_concepts.json.

Layer responsibilities:
  data_sources/sec.py        → fetches raw concept values from EDGAR
  financial_statements/      → assembles raw values into structured statements
  valuation_models/          → consumes finished statements for DCF, multiples, etc.

Usage:
    is = IncomeStatement(cik="320193", year=2023, period=Period.FY).build()
    is.summarize()
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Union
from financial_statements import FinancialStatement, Period

if TYPE_CHECKING:
    from financial_statements.balance_sheet import BalanceSheet
    from financial_statements.cash_flow_statement import CashFlowStatement


class IncomeStatement(FinancialStatement):

    _SECTIONS = FinancialStatement._CONCEPTS['income_statement']
    _CRITICAL = {
        'revenue':              'total_revenue',    # top line — nothing works without it
        'cost_of_revenue':      'cogs',             # gross_profit not always filed directly
        'operating_expenses':   'operating_income', # EBIT proxy, key for valuation
        'taxes_and_net_income': 'net_income',       # bottom line
    }

    def __init__(self, cik: str, year: int, period: Union[Period, str] = Period.FY):
        super().__init__(cik, year, period)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_line_item(self, section: str, line: str) -> Optional[float]:
        return self.data.get(section, {}).get(line, {}).get('val')

    def get_total_revenue(self) -> Optional[float]:
        return self.get_line_item('revenue', 'total_revenue')

    def get_cogs(self) -> Optional[float]:
        return self.get_line_item('cost_of_revenue', 'cogs')

    def get_gross_profit(self) -> Optional[float]:
        return self.get_line_item('cost_of_revenue', 'gross_profit')

    def get_opex(self) -> Optional[float]:
        return self.get_line_item('operating_expenses', 'total_operating_expenses')

    def get_operating_inc(self) -> Optional[float]:
        return self.get_line_item('operating_expenses', 'operating_income')

    def get_income_bef_tax(self) -> Optional[float]:
        return self.get_line_item('non_operating', 'income_before_tax')

    def get_tax(self) -> Optional[float]:
        return self.get_line_item('taxes_and_net_income', 'income_tax_expense')

    def get_net_income(self) -> Optional[float]:
        return self.get_line_item('taxes_and_net_income', 'net_income')

    # ------------------------------------------------------------------
    # Derived margins
    # ------------------------------------------------------------------

    def gross_margin(self) -> Optional[float]:
        rev, gp = self.get_total_revenue(), self.get_gross_profit()
        return gp / rev if rev and gp is not None else None

    def operating_margin(self) -> Optional[float]:
        rev, oi = self.get_total_revenue(), self.get_operating_inc()
        return oi / rev if rev and oi is not None else None

    def net_margin(self) -> Optional[float]:
        rev, ni = self.get_total_revenue(), self.get_net_income()
        return ni / rev if rev and ni is not None else None

    # ------------------------------------------------------------------
    # Validation — single period
    # ------------------------------------------------------------------

    def is_coherent(self, tolerance: float = 1.0) -> dict:
        """
        Checks internal consistency of the profitability cascade.
        Returns per-tier bool, or None if data is insufficient to check.
        """
        revenue      = self.get_total_revenue()
        cogs         = self.get_cogs()
        gross_profit = self.get_gross_profit()
        op_income    = self.get_operating_inc()
        net_income   = self.get_net_income()

        results = {}

        # Gross profit arithmetic: catches tag-scope mismatches at the top of the cascade
        if all(v is not None for v in [revenue, cogs, gross_profit]):
            results['gross_profit'] = abs(gross_profit - (revenue - cogs)) <= tolerance
        else:
            results['gross_profit'] = None

        # Margin cascade: gross >= operating >= net when the company is profitable
        if all(v is not None for v in [gross_profit, op_income, net_income]) and gross_profit > 0:
            results['margin_cascade'] = gross_profit >= op_income >= net_income
        else:
            results['margin_cascade'] = None

        return results

    def NetIncome_to_OperatingIncome(self) -> Optional[bool]:
        """
        Single-period red flag: net income exceeds operating income, meaning
        non-operating gains (asset sales, investment income) are driving profitability
        rather than core operations — a quality-of-earnings concern.
        Returns True if flagged.
        """
        op_income  = self.get_operating_inc()
        net_income = self.get_net_income()
        if op_income is None or net_income is None:
            return None
        return net_income > op_income

    # ------------------------------------------------------------------
    # Validation — cross-period (requires prior IncomeStatement)
    # ------------------------------------------------------------------

    def previous_period_check(self, prior: 'IncomeStatement', tolerance_pct: float = 0.05) -> dict:
        """
        Flags sharp gross margin changes and NI/OI divergence across periods.
        Requires a built IncomeStatement for the prior period.
        tolerance_pct: threshold for gross margin delta to be considered a red flag (default 5%).
        """
        results = {}

        cur_gm  = self.gross_margin()
        prior_gm = prior.gross_margin()
        if cur_gm is not None and prior_gm is not None:
            delta = cur_gm - prior_gm
            results['gross_margin_delta'] = delta
            results['gross_margin_flag']  = abs(delta) > tolerance_pct
        else:
            results['gross_margin_delta'] = None
            results['gross_margin_flag']  = None

        cur_ni, prior_ni = self.get_net_income(),    prior.get_net_income()
        cur_oi, prior_oi = self.get_operating_inc(), prior.get_operating_inc()
        if all(v is not None for v in [cur_ni, prior_ni, cur_oi, prior_oi]):
            results['ni_oi_divergence'] = (cur_ni > prior_ni) and (cur_oi < prior_oi)
        else:
            results['ni_oi_divergence'] = None

        return results

    # ------------------------------------------------------------------
    # Validation — cross-statement (requires CashFlowStatement or BalanceSheet)
    # ------------------------------------------------------------------

    def fall_to_sales(self, cash_flow: 'CashFlowStatement') -> Optional[float]:
        """
        Single-period cash conversion ratio: operating CF / revenue.
        Values consistently below 1.0 flag aggressive accrual accounting.
        """
        op_cf = cash_flow.get_operating_cf()
        rev   = self.get_total_revenue()
        if op_cf is None or not rev:
            return None
        return op_cf / rev

    def revenue_to_cash(self, cash_flow: 'CashFlowStatement', prior_is: 'IncomeStatement', prior_cf: 'CashFlowStatement') -> Optional[bool]:
        """
        Cross-period red flag: revenue grew but operating CF did not.
        Returns True if flagged. Requires prior-period IS and CF.
        """
        cur_rev,   prior_rev   = self.get_total_revenue(),      prior_is.get_total_revenue()
        cur_cf,    prior_cf_val = cash_flow.get_operating_cf(), prior_cf.get_operating_cf()
        if any(v is None for v in [cur_rev, prior_rev, cur_cf, prior_cf_val]):
            return None
        return (cur_rev > prior_rev) and (cur_cf <= prior_cf_val)

    def simple_reconciliation(self, bs_current: 'BalanceSheet', bs_prior: 'BalanceSheet', dividends_paid: float = 0.0, tolerance: float = 1.0) -> Optional[bool]:
        """
        Retained earnings bridge: NI ≈ RE_current − RE_prior + dividends_paid.
        This is the Statement of Retained Earnings equation expressed as a check.
        Pass cf.get_dividends_paid() or 0.0 for companies that don't pay dividends.
        """
        ni  = self.get_net_income()
        re_c = bs_current.get_retained_earnings()
        re_p = bs_prior.get_retained_earnings()
        print(f"debug: net_income: {ni}, retainedEarningsCurrent: {re_c}, retainedEarningsPrior: {re_p}, dividendsPaid: {dividends_paid}")
        if any(v is None for v in [ni, re_c, re_p]):
            return None
        return abs(ni - (re_c - re_p + dividends_paid)) <= tolerance
    
    def full_reconciliation(self, bs_current: 'BalanceSheet', bs_prior: 'BalanceSheet', cf: 'CashFlowStatement', dividends_paid: float = 0.0, tolerance: float = 1.0) -> Optional[bool]:
        """
        Full retained earnings bridge using the APIC bridge to isolate the RE
        impact of share repurchases:

            RE_impact_of_repurchases = repurchases + (APIC_c − APIC_p) − SBC − proceeds_from_stock
            NI ≈ (RE_c − RE_p) + dividends + RE_impact_of_repurchases

        APIC changes from SBC (up), stock proceeds (up), and the retired APIC
        balance on repurchased shares (down). Solving for that last term isolates
        how much of the repurchase cash spilled into RE vs absorbed by APIC.

        Falls back to the simple formula (repurchases = 0) when APIC is unavailable.
        Does not handle the treasury-stock method — those companies do not charge
        repurchases to RE, so simple_reconciliation() is correct for them.
        """
        ni    = self.get_net_income()
        re_c  = bs_current.get_retained_earnings()
        re_p  = bs_prior.get_retained_earnings()
        if any(v is None for v in [ni, re_c, re_p]):
            return None

        apic_c = bs_current.get_apic()
        apic_p = bs_prior.get_apic()
        sh_r   = cf.get_share_repurchased()   or 0.0
        sbc    = cf.get_sbc()                 or 0.0
        proc   = cf.get_proceeds_from_stock_issuance() or 0.0

        if apic_c is not None and apic_p is not None:
            ts_c = bs_current.get_treasury_stock() or 0.0
            ts_p = bs_prior.get_treasury_stock()   or 0.0
            if abs(ts_c - ts_p) > tolerance:
                # Treasury stock method: repurchases accumulate as contra-equity,
                # so they never touch RE. Simple bridge is correct for these companies.
                re_impact = 0.0
            else:
                # Constructive retirement: excess cost over par+APIC flows into RE.
                # APIC bridge isolates that portion without needing the equity rollforward.
                re_impact = sh_r + (apic_c - apic_p) - sbc - proc
        else:
            re_impact = sh_r  # fall back to CF amount when APIC unavailable

        print(
            f"full reconciliation: ni={ni}, re_c={re_c}, re_p={re_p}, "
            f"dividends={dividends_paid}, sh_r={sh_r}, apic_c={apic_c}, "
            f"apic_p={apic_p}, sbc={sbc}, proc={proc}, re_impact={re_impact}"
        )
        return abs(ni - (re_c - re_p + dividends_paid + re_impact)) <= tolerance

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summarize(self) -> None:
        if not self.data:
            print("No data — call build() first.")
            return

        meta = self.data.get('meta', {})
        print(f"\n{'='*60}")
        print(f"Income Statement — CIK {meta.get('cik')}  |  {meta.get('frame')}")
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
        gm = self.gross_margin()
        om = self.operating_margin()
        nm = self.net_margin()
        print(f"       {'Gross Margin':<45} {f'{gm:.1%}':>21}"    if gm is not None else f"       {'Gross Margin':<45} {'N/A':>21}")
        print(f"       {'Operating Margin':<45} {f'{om:.1%}':>21}" if om is not None else f"       {'Operating Margin':<45} {'N/A':>21}")
        print(f"       {'Net Margin':<45} {f'{nm:.1%}':>21}"       if nm is not None else f"       {'Net Margin':<45} {'N/A':>21}")

        missing = meta.get('missing_line_items', [])
        if missing:
            print(f"\n  ⚠  {len(missing)} line item(s) not found for this CIK:")
            for m in missing:
                print(f"       - [{m['section']}] {m['label']}")
                print(f"         Tried: {', '.join(m['candidates_tried'])}")

        coherence = self.is_coherent()
        gp_ok = coherence.get('gross_profit')
        mc_ok = coherence.get('margin_cascade')
        ni_flag = self.NetIncome_to_OperatingIncome()
        print(f"\n  {'─'*50}")
        print(f"  Coherence Checks")
        print(f"  {'─'*50}")
        print(f"       {'Gross profit arithmetic':<45} {'✓ PASS' if gp_ok else ('✗ FAIL' if gp_ok is False else 'N/A'):>21}")
        print(f"       {'Margin cascade':<45} {'✓ PASS' if mc_ok else ('✗ FAIL' if mc_ok is False else 'N/A'):>21}")
        print(f"       {'NI > OI (non-operating prop-up)':<45} {'⚠ FLAGGED' if ni_flag else ('✓ OK' if ni_flag is False else 'N/A'):>21}")
        print(f"{'='*60}\n")

    def __repr__(self) -> str:
        status = self.data.get('meta', {}).get('status', 'not built') if self.data else 'not built'
        return f"IncomeStatement(cik={self.cik}, year={self.year}, period={self.period.value}, status={status})"
