#!/usr/bin/env python3
"""
Description: DCF Model estimate intrinsic value by projecting future cash flows and discounting them to present value.

Method — Free Cash Flow to the Firm (FCFF), discounted at WACC:

    1. Historical FCFF  = operating CF − capex + interest × (1 − t) − SBC
         - interest is added back because FCFF is cash available to BOTH debt and
           equity holders (the WACC already prices the debt)
         - SBC is subtracted by default: it is a real cost paid in shares instead
           of cash, and operating CF adds it back (config: sbc_as_expense)
    2. Normalized FCFF margin = average(FCFF / revenue) over the history,
       so one unusual year does not drive the whole valuation
    3. Revenue grows at `initial_growth` in year 1, fading linearly to
       `terminal_growth` by the final projection year
    4. FCFF_t = revenue_t × FCFF margin, discounted at WACC (mid-year convention)
    5. Terminal value (Gordon growth) at the end of the projection, discounted back
    6. Equity value = enterprise value − debt + cash; ÷ diluted shares

Extras returned in result.details:
    projection   — year-by-year revenue / growth / FCFF / PV table
    sensitivity  — value per share across WACC × terminal growth
    scenarios    — bear / base / bull
    implied_growth — reverse DCF: the constant annual revenue growth over
                     reverse_dcf_years (default 10) that the current price implies
    equity_bridge  — enterprise value → equity value, line by line

Not applicable to banks, insurers and REITs (debt is operating raw material there).
"""
from __future__ import annotations
from typing import Optional

from valuation_models import ValuationModel, ValuationInputs, ValuationResult
from valuation_models.wacc import WACC


class DiscountedCashFlow(ValuationModel):

    NAME = "Discounted Cash Flow (FCFF)"

    def __init__(
        self,
        inputs:           ValuationInputs,
        wacc:             Optional[float] = None,
        initial_growth:   Optional[float] = None,
        terminal_growth:  Optional[float] = None,
        fcff_margin:      Optional[float] = None,
        projection_years: Optional[int]   = None,
        mid_year:         bool            = True,
    ):
        super().__init__(inputs)
        self._wacc_override     = wacc
        self._growth_override   = initial_growth
        self._margin_override   = fcff_margin
        self.terminal_growth    = terminal_growth if terminal_growth is not None else inputs.assumption('terminal_growth', 0.025)
        self.projection_years   = projection_years or inputs.assumption('projection_years', 5)
        self.mid_year           = mid_year
        self.wacc_model         = WACC(inputs)

    # ------------------------------------------------------------------
    # Drivers
    # ------------------------------------------------------------------
    def historical_fcff(self) -> list[Optional[float]]:
        """FCFF for each historical year (None where operating CF or capex is missing)."""
        h, t = self.history, self.inputs.assumption('marginal_tax_rate', 0.21)
        sbc_as_expense = self.inputs.assumption('sbc_as_expense', True)

        fcff = []
        for ocf, capex, interest, sbc in zip(h.series('operating_cf'), h.series('capex'),
                                             h.series('interest_expense'), h.series('sbc')):
            if ocf is None or capex is None:
                fcff.append(None)
                continue
            value = ocf - capex + (interest or 0.0) * (1 - t)
            if sbc_as_expense:
                value -= sbc or 0.0
            fcff.append(value)
        return fcff

    def fcff_margin(self) -> Optional[float]:
        if self._margin_override is not None:
            return self._margin_override
        margins = [f / r for f, r in zip(self.historical_fcff(), self.history.series('revenue')) if f is not None and r]
        return sum(margins) / len(margins) if margins else None

    def initial_growth(self) -> float:
        """Historical revenue CAGR, bounded to [terminal growth, max_initial_growth]."""
        if self._growth_override is not None:
            return self._growth_override
        cagr = self.history.cagr('revenue')
        cap  = self.inputs.assumption('max_initial_growth', 0.15)
        if cagr is None:
            return self.terminal_growth
        return min(max(cagr, self.terminal_growth), cap)

    def wacc(self) -> float:
        return self._wacc_override if self._wacc_override is not None else self.wacc_model.value()

    def growth_path(self, g0: float, gT: float) -> list[float]:
        """Linear fade from g0 (year 1) to gT (final year)."""
        n = self.projection_years
        if n == 1:
            return [g0]
        return [g0 + (gT - g0) * (t / (n - 1)) for t in range(n)]

    # ------------------------------------------------------------------
    # Core valuation
    # ------------------------------------------------------------------
    def _run(self, growths: list[float], gT: float, margin: float, wacc: float) -> dict:
        """
        Single DCF pass over one year per entry in `growths`, then a terminal
        value growing at gT. Returns projection, EV, equity and per-share value.
        """
        revenue    = self.history.latest('revenue')
        projection = []
        fcffs      = []
        for year_idx, g in enumerate(growths, start=1):
            revenue = revenue * (1 + g)
            fcff    = revenue * margin
            fcffs.append(fcff)
            shift   = 0.5 if self.mid_year else 0.0
            projection.append({
                'year':     self.history.years[-1] + year_idx,
                'growth':   g,
                'revenue':  revenue,
                'fcff':     fcff,
                'pv':       fcff / (1 + wacc) ** (year_idx - shift),
            })

        pv_fcff = self.present_value(fcffs, wacc, mid_year=self.mid_year)
        tv      = self.terminal_value(fcffs[-1], gT, wacc)
        pv_tv   = tv / (1 + wacc) ** len(growths)
        ev      = pv_fcff + pv_tv
        equity  = self.equity_from_enterprise(ev)

        return {
            'projection':       projection,
            'pv_fcff':          pv_fcff,
            'terminal_value':   tv,
            'pv_terminal':      pv_tv,
            'enterprise_value': ev,
            'equity_value':     equity,
            'value_per_share':  self.per_share(equity),
        }

    def value(self) -> ValuationResult:
        i = self.inputs
        if i.is_financial():
            return self._not_applicable(f"Financial company (SIC {i.sic}) — use P/B-ROE or a dividend model instead")
        if self.history.latest('revenue') is None:
            return self._not_applicable("No revenue history")

        margin = self.fcff_margin()
        if margin is None:
            return self._not_applicable("Cannot compute historical FCFF (missing operating CF or capex)")

        warnings = []
        wacc = self.wacc()
        gT   = self.terminal_growth
        if gT > i.risk_free_rate:
            warnings.append(f"Terminal growth {gT:.2%} capped at the risk-free rate {i.risk_free_rate:.2%} "
                            f"(no company outgrows the economy forever)")
            gT = i.risk_free_rate
        if wacc <= gT:
            return self._not_applicable(f"WACC {wacc:.2%} is not above terminal growth {gT:.2%}")
        g0 = self.initial_growth()
        if margin <= 0:
            warnings.append(f"Average FCFF margin is negative ({margin:.1%}) — DCF value is not meaningful")

        run = self._run(self.growth_path(g0, gT), gT, margin, wacc)

        tv_share = run['pv_terminal'] / run['enterprise_value'] if run['enterprise_value'] > 0 else None
        if tv_share is not None and tv_share > 0.75:
            warnings.append(f"Terminal value is {tv_share:.0%} of enterprise value — result is driven by long-run assumptions")
        if self._wacc_override is None:
            warnings += self.wacc_model.compute().warnings

        return self._result(
            run['value_per_share'],
            equity_value     = run['equity_value'],
            enterprise_value = run['enterprise_value'],
            assumptions = {
                'wacc':                 wacc,
                'initial_growth':       g0,
                'terminal_growth':      gT,
                'fcff_margin':          margin,
                'projection_years':     self.projection_years,
                'mid_year_convention':  self.mid_year,
                'sbc_as_expense':       i.assumption('sbc_as_expense', True),
                'net_debt':             i.net_debt(),
                'shares_outstanding':   i.shares_outstanding,
                'shares_source':        i.shares_source,
            },
            details = {
                'historical_fcff':        dict(zip(self.history.years, self.historical_fcff())),
                'projection':             run['projection'],
                'pv_fcff':                run['pv_fcff'],
                'pv_terminal':            run['pv_terminal'],
                'terminal_value_share':   tv_share,
                'sensitivity':            self.sensitivity(g0, gT, margin, wacc),
                'scenarios':              self.scenarios(g0, gT, margin, wacc),
                'implied_growth':         self.implied_growth(gT, margin, wacc),
                'reverse_dcf_years':      self.reverse_years(),
                'equity_bridge':          i.equity_bridge(run['enterprise_value']),
            },
            warnings = warnings,
        )

    # ------------------------------------------------------------------
    # Analysis around the base case
    # ------------------------------------------------------------------
    def sensitivity(self, g0: float, gT: float, margin: float, wacc: float,
                    wacc_steps=(-0.01, -0.005, 0.0, 0.005, 0.01),
                    growth_steps=(-0.005, 0.0, 0.005)) -> dict:
        """Value per share for each (WACC, terminal growth) pair around the base case."""
        grid = {}
        for dw in wacc_steps:
            for dg in growth_steps:
                w, g = wacc + dw, gT + dg
                grid[(round(w, 4), round(g, 4))] = self._run(self.growth_path(g0, g), g, margin, w)['value_per_share'] if w > g else None
        return grid

    def scenarios(self, g0: float, gT: float, margin: float, wacc: float) -> dict:
        """
        Bear: growth −3pp, margin −15%, WACC +1pp
        Base: as computed
        Bull: growth +3pp, margin +10%, WACC −0.5pp
        """
        cases = {
            'bear': (max(g0 - 0.03, 0.0), margin * 0.85, wacc + 0.01),
            'base': (g0, margin, wacc),
            'bull': (g0 + 0.03, margin * 1.10, max(wacc - 0.005, gT + 0.01)),
        }
        return {name: self._run(self.growth_path(g, gT), gT, m, w)['value_per_share'] for name, (g, m, w) in cases.items()}

    def reverse_years(self) -> int:
        return self.inputs.assumption('reverse_dcf_years', 10)

    def implied_growth(self, gT: float, margin: float, wacc: float,
                       lo: float = -0.20, hi: float = 0.60) -> Optional[float]:
        """
        Reverse DCF: the constant annual revenue growth over reverse_dcf_years
        (then terminal growth forever) that makes the DCF value equal the current
        price, holding margin and WACC fixed. One flat rate over a decade reads
        directly as "the market expects X% a year", unlike a year-1 rate that fades.
        Bisection works because value rises monotonically with growth when margin > 0.
        """
        price = self.inputs.price
        if price is None or margin <= 0:
            return None
        n = self.reverse_years()
        f = lambda g: self._run([g] * n, gT, margin, wacc)['value_per_share'] - price
        if f(lo) > 0 or f(hi) < 0:
            return None  # price is outside what any growth in [lo, hi] can justify
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
        return (lo + hi) / 2

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def summarize(self) -> None:
        result = self.value()
        result.summarize()
        if not result.applicable:
            return

        d = result.details
        print(f"\n  Projection")
        print(f"  {'-'*56}")
        print(f"       {'Year':<6} {'Growth':>8} {'Revenue':>18} {'FCFF':>16} {'PV':>16}")
        for row in d['projection']:
            print(f"       {row['year']:<6} {row['growth']:>8.1%} {row['revenue']:>18,.0f} {row['fcff']:>16,.0f} {row['pv']:>16,.0f}")
        print(f"       {'PV of FCFF':<34} {d['pv_fcff']:>32,.0f}")
        print(f"       {'PV of terminal value':<34} {d['pv_terminal']:>32,.0f}")

        print(f"\n  Equity bridge")
        print(f"  {'-'*56}")
        for label, amount, note in d['equity_bridge']:
            prefix = "   >>  " if label.startswith('=') else "       "
            print(f"{prefix}{label:<34} {amount:>22,.0f}" + (f"   [{note}]" if note else ''))

        print(f"\n  Sensitivity — value per share (rows: WACC, columns: terminal growth)")
        print(f"  {'-'*56}")
        waccs   = sorted({w for w, _ in d['sensitivity']})
        growths = sorted({g for _, g in d['sensitivity']})
        print(f"       {'':>8}" + ''.join(f"{g:>12.2%}" for g in growths))
        for w in waccs:
            cells = [d['sensitivity'][(w, g)] for g in growths]
            print(f"       {w:>8.2%}" + ''.join(f"{c:>12,.2f}" if c is not None else f"{'—':>12}" for c in cells))

        print(f"\n  Scenarios")
        print(f"  {'-'*56}")
        for name, vps in d['scenarios'].items():
            print(f"       {name.capitalize():<10} {f'${vps:,.2f}' if vps is not None else 'N/A':>14}")

        ig = d['implied_growth']
        if ig is not None:
            hist = self.history.cagr('revenue')
            print(f"\n  Reverse DCF")
            print(f"  {'-'*56}")
            print(f"       Today's price implies {ig:.1%} revenue growth a year for {d['reverse_dcf_years']} years,")
            print(f"       then {result.assumptions['terminal_growth']:.1%} forever (same margin and WACC).")
            if hist is not None:
                print(f"       Historical revenue CAGR: {hist:.1%} (FY{self.history.years[0]}–FY{self.history.years[-1]})")
        elif self.inputs.price is not None:
            print(f"\n  Reverse DCF: no growth rate between −20% and 60% a year justifies today's price")
        print(f"{'='*60}")
