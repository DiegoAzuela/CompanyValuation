#!/usr/bin/env python3
"""
Description: Asset-based values — what shareholders would get if the business stopped
operating. These are floors, not estimates of a going concern.

Net Current Asset Value (Benjamin Graham, "The Intelligent Investor", ch. 15):

    NCAV            = current assets − ALL liabilities (current and long-term)
    Net-net (NNWC)  = cash + 75% receivables + 50% inventory − all liabilities
    Buy rule        = price ≤ ⅔ × NCAV per share  ("net-net" stocks)

    Fixed assets get no credit at all, so a stock trading below NCAV is priced
    below what its working capital alone could repay.

Liquidation Value (Graham & Dodd, "Security Analysis", ch. 43):

    Each asset is marked down to what a forced sale typically recovers, then
    every liability is paid in full:

        cash and investments   100%      inventory          ~67%
        receivables             80%      PP&E / other       ~15%
        goodwill, intangibles, deferred taxes, lease ROU     0%

    Debt-security long-term investments recover 100%, strategic stakes 50%
    (same tag rule as the equity bridge). Rates live in config.json →
    valuation → liquidation_recovery.

Both use the latest fiscal-year balance sheet and current diluted shares.
Neither applies to banks or insurers, whose balance sheets are not split into
current / non-current.
"""
from __future__ import annotations
from typing import Optional

from valuation_models import ValuationModel, ValuationResult


class NetCurrentAssetValue(ValuationModel):

    NAME = "Net Current Asset Value (NCAV)"

    def value(self) -> ValuationResult:
        i, h = self.inputs, self.history
        if i.is_financial():
            return self._not_applicable(f"Financial company (SIC {i.sic}) — no current / non-current split")

        current_assets = h.value_at('current_assets', 0)
        liabilities    = i.total_liabilities()
        if current_assets is None or liabilities is None or not i.shares_outstanding:
            return self._not_applicable("Missing current assets, total liabilities or share count")

        ncav = current_assets - liabilities
        if ncav <= 0:
            return self._not_applicable(f"Liabilities exceed current assets by ${-ncav:,.0f} — not a net-net")

        nnwc = ((h.value_at('cash', 0) or 0.0) + (h.value_at('short_term_investments', 0) or 0.0)
                + 0.75 * (h.value_at('accounts_receivable', 0) or 0.0)
                + 0.50 * (h.value_at('inventory', 0) or 0.0)
                - liabilities)

        per_share = self.per_share(ncav)
        return self._result(
            per_share,
            equity_value = ncav,
            assumptions = {
                'current_assets':     current_assets,
                'total_liabilities':  liabilities,
                'shares_outstanding': i.shares_outstanding,
            },
            details = {
                'buy_below':          per_share * 2 / 3,
                'net_net_working_capital': nnwc,
                'nnwc_per_share':     self.per_share(nnwc),
                'price_to_ncav':      i.price / per_share if i.price else None,
            },
        )

    def summarize(self) -> None:
        result = self.value()
        result.summarize()
        if result.applicable:
            d = result.details
            print(f"  Graham buy-below (⅔ NCAV):  ${d['buy_below']:,.2f}")
            print(f"  Net-net working capital:    ${d['nnwc_per_share']:,.2f} per share")
            print(f"{'='*60}")


class LiquidationValue(ValuationModel):

    NAME = "Liquidation Value"

    # (metric, recovery key, label) — anything not listed lands in other_assets
    _CURRENT = [
        ('cash',                   'cash',                   'Cash and equivalents'),
        ('short_term_investments', 'short_term_investments', 'Short-term investments'),
        ('accounts_receivable',    'accounts_receivable',    'Accounts receivable'),
        ('inventory',              'inventory',              'Inventory'),
    ]
    _NONCURRENT = [
        ('ppe_net',                'ppe_net',                'PP&E, net'),
        ('goodwill',               'goodwill',               'Goodwill'),
        ('intangible_assets',      'intangible_assets',      'Intangible assets'),
        ('operating_lease_rou',    'operating_lease_rou',    'Operating lease ROU assets'),
        ('deferred_tax_assets',    'deferred_tax_assets',    'Deferred tax assets'),
    ]

    def recovery(self, key: str) -> float:
        return self.inputs.assumption('liquidation_recovery', {}).get(key, 0.0)

    def asset_lines(self) -> Optional[list[dict]]:
        """Each asset line with book value, recovery rate and recovered amount. None if totals are missing."""
        i, h = self.inputs, self.history
        current_total, total_assets = h.value_at('current_assets', 0), h.value_at('total_assets', 0)
        if current_total is None or total_assets is None:
            return None

        lines = []

        def add(label, book, key):
            if book:
                lines.append({'label': label, 'book': book, 'rate': self.recovery(key), 'recovered': book * self.recovery(key)})

        for metric, key, label in self._CURRENT:
            add(label, h.value_at(metric, 0), key)
        listed_current = sum(h.value_at(m, 0) or 0.0 for m, _, _ in self._CURRENT)
        add('Other current assets', max(current_total - listed_current, 0.0), 'other_assets')

        lti_cash, _ = i.long_term_investments_in_cash()
        lti_total   = h.value_at('long_term_investments', 0) or 0.0
        add('Long-term investments (debt securities)', lti_cash, 'long_term_investments_cash')
        add('Long-term investments (strategic)', lti_total - lti_cash, 'long_term_investments_other')
        for metric, key, label in self._NONCURRENT:
            add(label, h.value_at(metric, 0), key)
        listed_noncurrent = lti_total + sum(h.value_at(m, 0) or 0.0 for m, _, _ in self._NONCURRENT)
        add('Other non-current assets', max(total_assets - current_total - listed_noncurrent, 0.0), 'other_assets')
        return lines

    def value(self) -> ValuationResult:
        i = self.inputs
        if i.is_financial():
            return self._not_applicable(f"Financial company (SIC {i.sic}) — asset recoveries depend on loan quality")

        lines       = self.asset_lines()
        liabilities = i.total_liabilities()
        if lines is None or liabilities is None or not i.shares_outstanding:
            return self._not_applicable("Missing total assets, current assets, total liabilities or share count")

        recovered = sum(l['recovered'] for l in lines)
        equity    = recovered - liabilities
        if equity <= 0:
            return self._not_applicable(f"Recoverable assets fall ${-equity:,.0f} short of liabilities")

        return self._result(
            self.per_share(equity),
            equity_value = equity,
            assumptions = {
                'recoverable_assets': recovered,
                'total_liabilities':  liabilities,
                'shares_outstanding': i.shares_outstanding,
            },
            details = {'asset_lines': lines},
        )

    def summarize(self) -> None:
        result = self.value()
        result.summarize()
        if not result.applicable:
            return
        print(f"\n  Recovery by asset")
        print(f"  {'-'*56}")
        print(f"       {'Asset':<40} {'Book':>18} {'Rate':>6} {'Recovered':>18}")
        for l in result.details['asset_lines']:
            print(f"       {l['label']:<40} {l['book']:>18,.0f} {l['rate']:>6.0%} {l['recovered']:>18,.0f}")
        print(f"       {'− Total liabilities':<40} {'':>18} {'':>6} {-result.assumptions['total_liabilities']:>18,.0f}")
        print(f"   >>  {'Liquidation value':<40} {'':>18} {'':>6} {result.equity_value:>18,.0f}")
        print(f"{'='*60}")
