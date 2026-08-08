#!/usr/bin/env python3
"""
Description: Base class for all valuation models
"""

import time

class ValuationModels:
    """
    Base class for all valuation models

    Responsabilities:
        - 

    Subclasses:
        - 
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, bs: BalanceSheet, inc: IncomeStatement, cf: CashFlowStatement):
        self.bs     = bs
        self.inc    = inc
        self.cf     = cf
        self.year   = inc.year
        self.period = inc.period

    def value(self) -> Optional[float]:
        raise NotImplementedError

    def summarize(self) -> None:
        raise NotImplementedError

    # shared math utilities
    @staticmethod
    def present_value(cash_flows: list[float], rate: float) -> float:
        pass

    @staticmethod
    def terminal_value(final_cf: float, growth_rate: float, rate: float) -> float:
        pass