#!/usr/bin/env python3
"""
Description: Average Earnings Capitalization — apply a conservative multiple to average historical earnings.

Method (Benjamin Graham, "The Intelligent Investor", ch. 14 — defensive investor):
    "Current price should not be more than 15 times average earnings of the past three years."

    Average EPS  = average net income over the last N years ÷ current diluted shares
    Value        = multiple × average EPS

Why average net income ÷ current shares instead of averaging reported EPS?
    - Immune to stock splits (old EPS figures are not restated in older filings)
    - Credits buybacks: each remaining share now owns more of the earnings

Config (config.json → valuation):
    avg_earnings_multiple  default 15 (Graham's ceiling)
    avg_earnings_years     default 3
"""
from __future__ import annotations

from valuation_models import ValuationModel, ValuationResult


class AverageEarningsCapitalization(ValuationModel):

    NAME = "Average Earnings Capitalization"

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        years    = i.assumption('avg_earnings_years', 3)
        multiple = i.assumption('avg_earnings_multiple', 15)

        avg_net_income = h.average('net_income', n=years)
        if avg_net_income is None or not i.shares_outstanding:
            return self._not_applicable("Missing net income or share count")
        if avg_net_income <= 0:
            return self._not_applicable(f"Average net income over {years} years is negative")

        warnings = []
        available = len([v for v in h.series('net_income')[-years:] if v is not None])
        if available < years:
            warnings.append(f"Only {available} of {years} years of net income available")

        avg_eps = avg_net_income / i.shares_outstanding
        equity  = multiple * avg_net_income
        return self._result(
            multiple * avg_eps,
            equity_value = equity,
            assumptions = {
                'years_averaged':     years,
                'multiple':           multiple,
                'avg_net_income':     avg_net_income,
                'avg_eps':            avg_eps,
                'shares_outstanding': i.shares_outstanding,
            },
            details = {
                'price_to_avg_earnings': i.price / avg_eps if i.price else None,
            },
            warnings = warnings,
        )
