#!/usr/bin/env python3
"""
Description: Earnings Power Value (EPV) — value of today's sustainable earnings assuming ZERO growth.

Method (Bruce Greenwald, "Value Investing: From Graham to Buffett and Beyond"):

    1. Normalized EBIT     = average operating margin over the history × latest revenue
                             (smooths the business cycle instead of trusting one year)
    2. Maintenance capex   = capex − growth capex
                             growth capex = (average PP&E / revenue) × increase in revenue
                             i.e. only the spending needed to stand still is a true cost
    3. Adjusted EBIT       = normalized EBIT + normalized D&A − maintenance capex
                             (swap accounting depreciation for the real reinvestment need)
    4. EPV of operations   = adjusted EBIT × (1 − tax rate) / WACC
    5. EPV equity          = EPV of operations − debt + cash; ÷ diluted shares

How to read it next to the DCF:
    EPV > book value of invested capital → the business earns above its cost of capital
                                           (a "franchise")
    DCF  > EPV                           → the DCF value depends on growth; EPV is the
                                           no-growth floor you are not paying extra for
"""
from __future__ import annotations
from typing import Optional

from valuation_models import ValuationModel, ValuationInputs, ValuationResult
from valuation_models.wacc import WACC


class EarningsPowerValue(ValuationModel):

    NAME = "Earnings Power Value (EPV)"

    def __init__(self, inputs: ValuationInputs, wacc: Optional[float] = None):
        super().__init__(inputs)
        self._wacc_override = wacc
        self.wacc_model     = WACC(inputs)

    def maintenance_capex_ratio(self) -> Optional[float]:
        """Average maintenance capex as a share of revenue (Greenwald's PP&E/sales method)."""
        h = self.history
        ppe_to_sales = h.average_ratio('ppe_net', 'revenue')
        revenue, capex = h.series('revenue'), h.series('capex')
        if ppe_to_sales is None:
            return None

        ratios = []
        for t in range(1, len(h)):
            if None in (revenue[t], revenue[t - 1], capex[t]) or not revenue[t]:
                continue
            growth_capex = max(ppe_to_sales * (revenue[t] - revenue[t - 1]), 0.0)
            maintenance  = min(max(capex[t] - growth_capex, 0.0), capex[t])
            ratios.append(maintenance / revenue[t])
        return sum(ratios) / len(ratios) if ratios else None

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        if i.is_financial():
            return self._not_applicable(f"Financial company (SIC {i.sic}) — EBIT-based value does not apply")

        revenue = h.latest('revenue')
        margin  = h.average_ratio('operating_income', 'revenue')
        if revenue is None or margin is None:
            return self._not_applicable("Missing revenue or operating income history")

        warnings = []
        da_ratio    = h.average_ratio('depreciation', 'revenue')
        maint_ratio = self.maintenance_capex_ratio()
        if da_ratio is None or maint_ratio is None:
            warnings.append("D&A or capex history missing — using unadjusted EBIT")
            da_ratio = maint_ratio = 0.0
        if len(h) < 2:
            warnings.append("Only one year of history — maintenance capex equals total capex")

        normalized_ebit = margin * revenue
        adjusted_ebit   = normalized_ebit + (da_ratio - maint_ratio) * revenue
        tax_rate        = i.tax_rate()
        nopat           = adjusted_ebit * (1 - tax_rate)
        wacc            = self._wacc_override if self._wacc_override is not None else self.wacc_model.value()

        epv_operations = nopat / wacc
        equity         = self.equity_from_enterprise(epv_operations)
        if nopat <= 0:
            warnings.append("Normalized after-tax earnings are negative — EPV is not meaningful")
        if self._wacc_override is None:
            warnings += self.wacc_model.compute().warnings

        book_equity = h.latest('total_equity')
        return self._result(
            self.per_share(equity),
            equity_value     = equity,
            enterprise_value = epv_operations,
            assumptions = {
                'avg_operating_margin':      margin,
                'normalized_ebit':           normalized_ebit,
                'da_margin':                 da_ratio,
                'maintenance_capex_margin':  maint_ratio,
                'adjusted_ebit':             adjusted_ebit,
                'tax_rate':                  tax_rate,
                'wacc':                      wacc,
                'net_debt':                  i.net_debt(),
            },
            details = {
                'nopat':              nopat,
                'epv_to_book_equity': equity / book_equity if book_equity and book_equity > 0 else None,
            },
            warnings = warnings,
        )
