#!/usr/bin/env python3
"""
Description: Base class for all valuation models
"""
from __future__ import annotations
from typing import Optional

from valuation_models.inputs import FinancialHistory, ValuationInputs, ValuationResult


class ValuationModel:
    """
    Base class for all valuation models

    Responsabilities:
        - Holds the ValuationInputs a model consumes
        - Provides shared discounting math used by DCF, EPV, DDM, etc.
        - Bridges enterprise value → equity value → value per share

    Subclasses:
        - DiscountedCashFlow       (dcf_valuation.py)
        - EarningsPowerValue       (earning_power.py)
        - AverageEarningsCapitalization (earnings_capitalization.py)
        - PeterLynchFairValue      (peter_lynch_fairvalue.py)
        - DividendDiscountModel    (dividend_discount.py)
        - TradingMultiples         (trading_multiples.py)
    """

    NAME = "Valuation Model"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, inputs: ValuationInputs):
        self.inputs  = inputs
        self.history = inputs.history

    def value(self) -> ValuationResult:
        raise NotImplementedError

    def summarize(self) -> None:
        self.value().summarize()

    # ------------------------------------------------------------------
    # Shared result helpers
    # ------------------------------------------------------------------
    def _result(self, value_per_share: Optional[float], **kwargs) -> ValuationResult:
        """Builds a result for this model with the current price filled in."""
        return ValuationResult(model=self.NAME, value_per_share=value_per_share, price=self.inputs.price, **kwargs)

    def _not_applicable(self, reason: str) -> ValuationResult:
        return ValuationResult.not_applicable(self.NAME, reason, price=self.inputs.price)

    def equity_from_enterprise(self, enterprise_value: float) -> float:
        """EV − debt (incl. leases if configured) + cash and investments."""
        return enterprise_value - self.inputs.net_debt()

    def per_share(self, equity_value: Optional[float]) -> Optional[float]:
        shares = self.inputs.shares_outstanding
        return equity_value / shares if equity_value is not None and shares else None

    # ------------------------------------------------------------------
    # Shared math utilities
    # ------------------------------------------------------------------
    @staticmethod
    def present_value(cash_flows: list[float], rate: float, mid_year: bool = False) -> float:
        """
        Discounts a series of annual cash flows to today.
        cash_flows[0] is received in year 1 — at year-end by default, or at
        mid-year (t − 0.5) when mid_year=True, which better matches cash that
        arrives throughout the year.
        """
        shift = 0.5 if mid_year else 0.0
        return sum(cf / (1 + rate) ** (t - shift) for t, cf in enumerate(cash_flows, start=1))

    @staticmethod
    def terminal_value(final_cf: float, growth_rate: float, rate: float) -> float:
        """
        Gordon growth terminal value at the end of the final projection year:
            TV = CF_final × (1 + g) / (r − g)
        The result is a future value — discount it by (1 + r)^n before adding to PV.
        """
        if rate <= growth_rate:
            raise ValueError(f"Discount rate ({rate:.2%}) must exceed terminal growth ({growth_rate:.2%})")
        return final_cf * (1 + growth_rate) / (rate - growth_rate)


__all__ = ['ValuationModel', 'ValuationInputs', 'ValuationResult', 'FinancialHistory']
