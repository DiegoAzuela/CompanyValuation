#!/usr/bin/env python3
"""
Description: Weighted Average Cost of Capital — the discount rate for firm-level cash flows (FCFF).

    WACC = E/(D+E) × Ke  +  D/(D+E) × Kd × (1 − t)

    Ke (cost of equity) = risk-free rate + beta × equity risk premium      (CAPM)
    Kd (cost of debt)   = risk-free rate + default spread for a synthetic credit
                          rating derived from interest coverage (EBIT / interest)
    t                   = marginal tax rate (the rate the interest tax shield saves)
    E, D                = market value of equity, book value of debt (incl. leases)

Why a synthetic rating instead of interest expense / debt?
    Interest expense reflects coupons locked in years ago. A DCF needs what the
    company would pay to borrow today, which is today's risk-free rate plus a
    spread that depends on how safely it covers its interest.

Spread table source: Damodaran, "Ratings, Interest Coverage Ratios and Default
Spread" (large non-financial firms). Stored in config.json → valuation →
synthetic_rating_spreads so it can be refreshed each January.

Usage:
    wacc = WACC(inputs)
    wacc.value()        # → 0.0874
    wacc.summarize()
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from valuation_models.inputs import ValuationInputs

# Prefix of the single warning line listing market inputs taken from config.json
PLACEHOLDER_WARNING = "Placeholder market inputs from config.json"


@dataclass
class WaccBreakdown:
    cost_of_equity:         float
    pre_tax_cost_of_debt:   float
    after_tax_cost_of_debt: float
    equity_weight:          float
    debt_weight:            float
    wacc:                   float
    interest_coverage:      Optional[float] = None
    coverage_method:        str             = 'none'
    synthetic_rating:       Optional[str]   = None
    implied_coupon_rate:    Optional[float] = None   # interest / avg debt, for reference only
    warnings:               list[str]       = field(default_factory=list)


class WACC:

    def __init__(self, inputs: ValuationInputs):
        self.inputs  = inputs
        self.history = inputs.history
        self._breakdown: Optional[WaccBreakdown] = None

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------
    def cost_of_equity(self) -> float:
        i = self.inputs
        return i.risk_free_rate + i.beta * i.equity_risk_premium

    def financial_debt(self, offset: int = 0) -> float:
        """Borrowings only (no leases) — the debt that interest expense is paid on."""
        return sum(self.history.value_at(p, offset) or 0.0
                   for p in ('short_term_debt', 'current_portion_ltd', 'long_term_debt'))

    def coupon_rate_at(self, offset: int) -> Optional[float]:
        """Interest / financial debt for the year `offset` years back (None if either is missing)."""
        interest = self.history.value_at('interest_expense', offset)
        debt     = self.financial_debt(offset)
        return interest / debt if interest and debt > 0 else None

    def interest_coverage(self) -> tuple[Optional[float], str]:
        """
        Latest-year EBIT / interest, resolved through a fallback chain that works
        for any filer:

          1. reported  — latest year filed interest (any tag in the concept map's
                         candidate chain, incl. cash interest paid as a last resort)
          2. estimated — latest debt × the most recent borrowing rate the company
                         did report (interest / debt in that year)
          3. none      — no interest ever reported; caller uses the default spread

        Returns (coverage, method).
        """
        h    = self.history
        ebit = h.value_at('operating_income', 0)
        if ebit is None:
            return None, 'none'

        interest = h.value_at('interest_expense', 0)
        if interest:
            return ebit / interest, 'reported'

        debt = self.financial_debt(0)
        for offset in range(1, len(h)):
            rate = self.coupon_rate_at(offset)
            if rate is not None and debt > 0:
                return ebit / (debt * rate), f'estimated from FY{h.years[-1 - offset]} rate {rate:.2%}'
        return None, 'none'

    def synthetic_rating(self, coverage: float) -> tuple[str, float]:
        """Maps interest coverage to (rating, default spread) using the config table."""
        table = sorted(self.inputs.assumption('synthetic_rating_spreads', []), key=lambda row: row[0], reverse=True)
        for min_coverage, rating, spread in table:
            if coverage >= min_coverage:
                return rating, spread
        return ('D', table[-1][2]) if table else ('n/a', self.inputs.assumption('default_credit_spread', 0.015))

    def spread_table_warning(self, today: Optional[date] = None) -> Optional[str]:
        """Warning when the spread table's as_of month is older than spreads_max_age_months."""
        as_of = self.inputs.assumption('synthetic_rating_spreads_as_of')
        if not as_of:
            return "Spread table has no as_of date — check it against Damodaran's latest ratings data"
        year, month = (int(x) for x in as_of.split('-')[:2])
        today = today or date.today()
        age   = (today.year - year) * 12 + today.month - month
        limit = self.inputs.assumption('spreads_max_age_months', 15)
        if age > limit:
            return f"Spread table is from {as_of} ({age} months old) — refresh it from Damodaran's ratings data"
        return None

    def implied_coupon_rate(self) -> Optional[float]:
        """Latest-year interest / average debt (reference only). None if not filed in the latest year."""
        interest = self.history.value_at('interest_expense', 0)
        avg_debt = (self.financial_debt(0) + self.financial_debt(1)) / 2 if len(self.history) > 1 else self.financial_debt(0)
        return interest / avg_debt if interest and avg_debt > 0 else None

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    def compute(self) -> WaccBreakdown:
        if self._breakdown is not None:
            return self._breakdown

        i        = self.inputs
        warnings = []
        ke       = self.cost_of_equity()

        # Cost of debt
        coverage, coverage_method = self.interest_coverage()
        if coverage is not None:
            rating, spread = self.synthetic_rating(coverage)
            if coverage_method != 'reported':
                warnings.append(f"Latest interest expense not filed — coverage {coverage_method}")
        else:
            rating, spread = 'n/a', i.assumption('default_credit_spread', 0.015)
            if self.financial_debt(0) > 0:
                warnings.append(f"No interest expense in the history — using default credit spread {spread:.2%}")
        if coverage is not None and (stale := self.spread_table_warning()):
            warnings.append(stale)
        kd_pre   = i.risk_free_rate + spread
        kd_after = kd_pre * (1 - i.assumption('marginal_tax_rate', 0.21))

        # Weights
        debt       = i.total_debt()
        market_cap = i.market_cap()
        if market_cap:
            wd = debt / (debt + market_cap) if debt + market_cap > 0 else 0.0
        else:
            wd = i.assumption('default_debt_weight', 0.10) if debt > 0 else 0.0
            warnings.append(f"No share price — using assumed debt weight {wd:.0%} instead of market values")
        we = 1 - wd

        wacc = we * ke + wd * kd_after

        placeholders = [n for n in ('risk_free_rate', 'equity_risk_premium', 'beta') if n in i.defaults_used]
        if placeholders:
            warnings.append(f"{PLACEHOLDER_WARNING}: {', '.join(placeholders)}")

        self._breakdown = WaccBreakdown(
            cost_of_equity         = ke,
            pre_tax_cost_of_debt   = kd_pre,
            after_tax_cost_of_debt = kd_after,
            equity_weight          = we,
            debt_weight            = wd,
            wacc                   = wacc,
            interest_coverage      = coverage,
            coverage_method        = coverage_method,
            synthetic_rating       = rating,
            implied_coupon_rate    = self.implied_coupon_rate(),
            warnings               = warnings,
        )
        return self._breakdown

    def value(self) -> float:
        return self.compute().wacc

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def summarize(self) -> None:
        b, i = self.compute(), self.inputs
        print(f"\n{'='*60}")
        print(f"WACC — {i.ticker}")
        print(f"{'='*60}")
        print(f"  Cost of Equity (CAPM)")
        print(f"       {'Risk-free rate':<36} {i.risk_free_rate:>10.2%}")
        print(f"       {'Beta':<36} {i.beta:>10.2f}")
        print(f"       {'Equity risk premium':<36} {i.equity_risk_premium:>10.2%}")
        print(f"   >>  {'Cost of equity':<36} {b.cost_of_equity:>10.2%}")
        print(f"\n  Cost of Debt")
        cov = f"{b.interest_coverage:.1f}x" if b.interest_coverage is not None else 'N/A'
        print(f"       {'Interest coverage (EBIT / interest)':<36} {cov:>10}   ({b.coverage_method})")
        print(f"       {'Synthetic rating':<36} {b.synthetic_rating:>10}")
        print(f"       {'Pre-tax cost of debt':<36} {b.pre_tax_cost_of_debt:>10.2%}")
        if b.implied_coupon_rate is not None:
            print(f"       {'(Reference: interest / avg debt)':<36} {b.implied_coupon_rate:>10.2%}")
        print(f"   >>  {'After-tax cost of debt':<36} {b.after_tax_cost_of_debt:>10.2%}")
        print(f"\n  Weights")
        print(f"       {'Equity':<36} {b.equity_weight:>10.1%}")
        print(f"       {'Debt (incl. leases)':<36} {b.debt_weight:>10.1%}")
        print(f"\n   >>  {'WACC':<36} {b.wacc:>10.2%}")
        if b.warnings:
            print(f"\n  ⚠  Warnings")
            for w in b.warnings:
                print(f"       - {w}")
        print(f"{'='*60}")
