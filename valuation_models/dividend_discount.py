#!/usr/bin/env python3
"""
Description: Dividend Discount Model (DDM) and dividend record.

Method — single-stage Gordon growth on dividends, discounted at the cost of equity:

    Value = DPS₀ × (1 + g) / (Ke − g)

    DPS₀ = latest dividends paid ÷ diluted shares
    Ke   = cost of equity from CAPM (same inputs as the WACC)
    g    = historical DPS growth, capped at ddm_max_growth (default 4%) — a
           single-stage model assumes this growth lasts forever, so it must be
           close to long-run economic growth

Buyback-adjusted value (details['buyback_adjusted_value']):
    Many companies return more cash through buybacks than dividends (Apple:
    ~6× more). A dividend-only model undervalues them. The "augmented
    dividend" variant (Damodaran) applies the same formula to average
    (dividends + buybacks) per share.

Dividend record (details['dividend_record']):
    years paid, consecutive per-share increases, payout ratio, yield.

Not applicable to companies that do not pay dividends.
"""
from __future__ import annotations
from typing import Optional

from valuation_models import ValuationModel, ValuationInputs, ValuationResult
from valuation_models.wacc import WACC, PLACEHOLDER_WARNING


class DividendDiscountModel(ValuationModel):

    NAME = "Dividend Discount Model (DDM)"

    def __init__(self, inputs: ValuationInputs, cost_of_equity: Optional[float] = None, growth: Optional[float] = None):
        super().__init__(inputs)
        self._ke_override     = cost_of_equity
        self._growth_override = growth

    def dividend_record(self) -> dict:
        h, i = self.history, self.inputs
        divs   = h.series('dividends_paid')
        shares = h.series('shares_diluted')
        dps    = [d / s if d and s else None for d, s in zip(divs, shares)]

        increases = 0
        if not h.split_detected():
            for prev, cur in zip(reversed(dps[:-1]), reversed(dps[1:])):
                if prev is None or cur is None or cur <= prev:
                    break
                increases += 1

        net_income = h.latest('net_income')
        latest_div = h.latest('dividends_paid') or 0.0
        dps_now    = latest_div / i.shares_outstanding if i.shares_outstanding else None
        return {
            'years_paid':             sum(1 for d in divs if d),
            'years_in_history':       len(h),
            'consecutive_increases':  increases if not h.split_detected() else None,
            'dps_by_year':            dict(zip(h.years, dps)),
            'payout_ratio':           latest_div / net_income if net_income and net_income > 0 else None,
            'dividend_yield':         dps_now / i.price if dps_now and i.price else None,
        }

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        dividends = h.latest('dividends_paid')
        if not dividends or not i.shares_outstanding:
            return self._not_applicable("Company does not pay dividends")

        warnings = []
        wacc_model = WACC(i)
        ke = self._ke_override if self._ke_override is not None else wacc_model.cost_of_equity()

        cap = i.assumption('ddm_max_growth', 0.04)
        if self._growth_override is not None:
            g = self._growth_override
        else:
            hist_g = h.per_share_cagr('dividends_paid')
            g = min(hist_g, cap) if hist_g is not None else 0.0
            if hist_g is not None and hist_g > cap:
                warnings.append(f"Historical dividend growth {hist_g:.1%} capped at {cap:.1%} for a perpetual model")
        if g >= ke:
            return self._not_applicable(f"Dividend growth {g:.2%} is not below cost of equity {ke:.2%}")

        dps0  = dividends / i.shares_outstanding
        value = dps0 * (1 + g) / (ke - g)

        # Augmented dividends: average (dividends + buybacks) over the history
        buybacks = h.average('share_repurchases')
        avg_divs = h.average('dividends_paid')
        buyback_value = None
        if buybacks and avg_divs:
            total_payout_ps = (avg_divs + buybacks) / i.shares_outstanding
            buyback_value   = total_payout_ps * (1 + g) / (ke - g)
            if buybacks > avg_divs:
                warnings.append(f"Buybacks are {buybacks / avg_divs:.1f}× dividends — the dividend-only value "
                                f"understates cash returned; see buyback-adjusted value")

        if self._ke_override is None:
            warnings += [w for w in wacc_model.compute().warnings if w.startswith(PLACEHOLDER_WARNING)]

        return self._result(
            value,
            equity_value = value * i.shares_outstanding,
            assumptions = {
                'dps':             dps0,
                'dividend_growth': g,
                'cost_of_equity':  ke,
            },
            details = {
                'dividend_record':        self.dividend_record(),
                'buyback_adjusted_value': buyback_value,
            },
            warnings = warnings,
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def summarize(self) -> None:
        result = self.value()
        result.summarize()
        if not result.applicable:
            return
        rec = result.details['dividend_record']
        bbv = result.details['buyback_adjusted_value']
        print(f"\n  Dividend record")
        print(f"  {'-'*50}")
        print(f"       {'Years paid':<36} {rec['years_paid']} of {rec['years_in_history']}")
        inc = rec['consecutive_increases']
        print(f"       {'Consecutive per-share increases':<36} {inc if inc is not None else 'N/A (stock split)'}")
        if rec['payout_ratio'] is not None:
            print(f"       {'Payout ratio':<36} {rec['payout_ratio']:.1%}")
        if rec['dividend_yield'] is not None:
            print(f"       {'Dividend yield':<36} {rec['dividend_yield']:.2%}")
        if bbv is not None:
            print(f"\n       {'Buyback-adjusted value per share':<36} ${bbv:,.2f}")
        print(f"{'='*60}")
