#!/usr/bin/env python3
"""
Description: Peter Lynch Fair Value — a fairly priced stock's P/E equals its earnings growth rate.

Method (Peter Lynch, "One Up on Wall Street", ch. 13):
    "The P/E ratio of any company that's fairly priced will equal its growth rate."
    He also credits dividends:  fair P/E = EPS growth % + dividend yield %

    Fair value = latest EPS × min(growth % + dividend yield %, cap)

    growth  = EPS CAGR over the history (net income per diluted share)
    cap     = 25 by default — Lynch distrusted growth above ~25% as unsustainable

Lynch ratio (shown when a price is available):
    (growth % + dividend yield %) / P/E   →  < 1 poor,  ~1.5 okay,  ≥ 2 attractive

Not applicable when earnings are shrinking or negative — the method assumes growth.
"""
from __future__ import annotations

from valuation_models import ValuationModel, ValuationResult


class PeterLynchFairValue(ValuationModel):

    NAME = "Peter Lynch Fair Value"

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        warnings = []

        net_income = h.latest('net_income')
        if net_income is None or not i.shares_outstanding:
            return self._not_applicable("Missing net income or share count")
        eps = net_income / i.shares_outstanding
        if eps <= 0:
            return self._not_applicable("Latest earnings are negative")

        growth = h.per_share_cagr('net_income')
        if growth is None:
            return self._not_applicable("Not enough history to measure EPS growth")
        if growth <= 0:
            return self._not_applicable(f"EPS growth is {growth:.1%} — the method assumes a growing company")
        if h.split_detected():
            warnings.append("Stock split detected — growth measured on total net income instead of EPS")

        dps            = (h.latest('dividends_paid') or 0.0) / i.shares_outstanding
        dividend_yield = dps / i.price if i.price else 0.0
        if dps and not i.price:
            warnings.append("No share price — dividend yield excluded from fair P/E")

        cap      = i.assumption('lynch_max_growth', 25)
        fair_pe  = min(growth * 100 + dividend_yield * 100, cap)
        if growth * 100 + dividend_yield * 100 > cap:
            warnings.append(f"Growth + yield capped at {cap} (Lynch: >25% growth rarely lasts)")

        pe = i.price / eps if i.price else None
        return self._result(
            fair_pe * eps,
            assumptions = {
                'eps':               eps,
                'eps_growth':        growth,
                'dividend_yield':    dividend_yield,
                'fair_pe':           fair_pe,
                'years_measured':    len(h),
            },
            details = {
                'pe':          pe,
                'lynch_ratio': (growth * 100 + dividend_yield * 100) / pe if pe else None,
            },
            warnings = warnings,
        )
