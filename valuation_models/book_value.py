#!/usr/bin/env python3
"""
Description: Book-value models — value anchored on shareholders' equity.

Justified Price-to-Book (ROE model):

    Justified P/B = (ROE − g) / (Ke − g)
    Value         = justified P/B × book value per share

    A company earning exactly its cost of equity (ROE = Ke) is worth book value;
    every point of ROE above Ke earns a premium. This is the standard model for
    banks and insurers, where the DCF does not apply.

        ROE = average of net income / average equity (opening + closing) over the history
        Ke  = CAPM cost of equity (same as the WACC)
        g   = terminal growth, capped at the risk-free rate

Graham Number ("The Intelligent Investor", ch. 14):

    Graham Number = √(22.5 × EPS × book value per share)

    22.5 = Graham's maximum P/E of 15 × maximum P/B of 1.5 for a defensive
    investor. A stock below its Graham number passes both tests combined.

Both use current diluted shares, so EPS and book value per share credit buybacks.
Book value shrinks when a company buys back stock above book, so for heavy
repurchasers (e.g. Apple) both models understate value — they warn when ROE > 40%.
"""
from __future__ import annotations
import math
from typing import Optional

from valuation_models import ValuationModel, ValuationInputs, ValuationResult
from valuation_models.wacc import WACC


def average_roe(history) -> Optional[float]:
    """Average of net income / average equity, for every year with an opening balance."""
    ni, eq = history.series('net_income'), history.series('total_equity')
    rates = [ni[t] / ((eq[t] + eq[t - 1]) / 2)
             for t in range(1, len(history))
             if None not in (ni[t], eq[t], eq[t - 1]) and eq[t] + eq[t - 1] > 0]
    if not rates and ni and ni[-1] is not None and eq[-1]:
        rates = [ni[-1] / eq[-1]]  # single year: closing equity only
    return sum(rates) / len(rates) if rates else None


class JustifiedPriceToBook(ValuationModel):

    NAME = "Justified P/B (ROE)"

    def __init__(self, inputs: ValuationInputs, cost_of_equity: Optional[float] = None,
                 growth: Optional[float] = None):
        super().__init__(inputs)
        self._ke_override     = cost_of_equity
        self._growth_override = growth

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        equity = h.value_at('total_equity', 0)
        if equity is None or not i.shares_outstanding:
            return self._not_applicable("Missing total equity or share count")
        if equity <= 0:
            return self._not_applicable("Negative book value (buybacks or losses exceed paid-in capital)")

        roe = average_roe(h)
        if roe is None:
            return self._not_applicable("Cannot compute ROE (missing net income or equity)")

        ke = self._ke_override if self._ke_override is not None else WACC(i).cost_of_equity()
        g  = self._growth_override if self._growth_override is not None else min(
             i.assumption('terminal_growth', 0.025), i.risk_free_rate)
        if ke <= g:
            return self._not_applicable(f"Cost of equity {ke:.2%} is not above growth {g:.2%}")
        if roe <= g:
            return self._not_applicable(f"ROE {roe:.1%} does not exceed growth {g:.1%}")

        warnings = []
        if roe > 0.40:
            warnings.append(f"ROE of {roe:.0%} reflects a book value shrunk by buybacks — P/B is a weak anchor here")

        justified_pb = (roe - g) / (ke - g)
        bvps         = self.per_share(equity)
        tangible     = equity - (h.value_at('goodwill', 0) or 0.0) - (h.value_at('intangible_assets', 0) or 0.0)

        return self._result(
            justified_pb * bvps,
            equity_value = justified_pb * equity,
            assumptions = {
                'average_roe':        roe,
                'cost_of_equity':     ke,
                'growth':             g,
                'justified_pb':       justified_pb,
                'book_value':         equity,
                'shares_outstanding': i.shares_outstanding,
            },
            details = {
                'book_value_per_share':          bvps,
                'tangible_book_value_per_share': self.per_share(tangible),
                'price_to_book':                 i.price / bvps if i.price else None,
            },
            warnings = warnings,
        )


class GrahamNumber(ValuationModel):

    NAME = "Graham Number"

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        net_income, equity = h.value_at('net_income', 0), h.value_at('total_equity', 0)
        if net_income is None or equity is None or not i.shares_outstanding:
            return self._not_applicable("Missing net income, total equity or share count")
        if net_income <= 0 or equity <= 0:
            return self._not_applicable("Needs positive earnings and positive book value")

        multiple = i.assumption('graham_number_multiple', 22.5)
        eps, bvps = self.per_share(net_income), self.per_share(equity)

        warnings = []
        roe = net_income / equity
        if roe > 0.40:
            warnings.append(f"ROE of {roe:.0%} reflects a book value shrunk by buybacks — the Graham number understates value")

        return self._result(
            math.sqrt(multiple * eps * bvps),
            assumptions = {
                'multiple':             multiple,
                'eps':                  eps,
                'book_value_per_share': bvps,
                'shares_outstanding':   i.shares_outstanding,
            },
            details = {
                'pe_times_pb': (i.price / eps) * (i.price / bvps) if i.price else None,
            },
            warnings = warnings,
        )
