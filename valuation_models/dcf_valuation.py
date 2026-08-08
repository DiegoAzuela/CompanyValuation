#!/usr/bin/env python3
"""
Description: DCF Model estimate intrinsic value by projecting future cash flows and discounting them to present value.
"""

class DiscountedCashFlow(ValuationModel):

    def __init__(self, cik: str):
        super().__init__(cik)
