#!/usr/bin/env python3
"""
Description: Trading Multiples — value the company at the median multiple its peers trade at.

Method:
    1. For each peer: latest fiscal-year fundamentals from the SEC + its share price
    2. Compute each peer's multiples:
         P/E        = price / EPS                         (equity multiples)
         P/B        = market cap / book equity
         P/S        = market cap / revenue
         EV/EBIT    = enterprise value / operating income (firm multiples)
         EV/EBITDA  = enterprise value / (operating income + D&A)
    3. Take the MEDIAN of each multiple across peers (robust to one outlier peer)
    4. Apply it to the company's own metric:
         equity multiples → equity value directly
         EV multiples     → enterprise value, then subtract net debt
    5. Value per share = median of the implied values across all multiples

Peer prices are passed in until a market data source exists:
    TradingMultiples(inputs, peers={"MSFT": 510.0, "GOOGL": 245.0, "META": 720.0})

Notes:
    - Choose peers with similar business models, growth and margins — the
      result is only as good as the peer group
    - Peers' fiscal years may end in different months; latest 10-K is used for each
    - Financial companies only use P/E and P/B (EV is not meaningful for them)
"""
from __future__ import annotations
from statistics import median
from typing import Callable, Optional

from db.tickers import TickerDB
from valuation_models import ValuationModel, ValuationInputs, ValuationResult
from valuation_models.inputs import FinancialHistory


# name → (peer multiple from ValuationInputs, target metric, is_ev_multiple)
_MULTIPLES: dict[str, tuple[Callable, Callable, bool]] = {
    'P/E': (
        lambda p: p.price / (p.history.latest('net_income') / p.shares_outstanding),
        lambda t: t.history.latest('net_income'),
        False,
    ),
    'P/B': (
        lambda p: p.market_cap() / p.history.latest('total_equity'),
        lambda t: t.history.latest('total_equity'),
        False,
    ),
    'P/S': (
        lambda p: p.market_cap() / p.history.latest('revenue'),
        lambda t: t.history.latest('revenue'),
        False,
    ),
    'EV/EBIT': (
        lambda p: p.enterprise_value() / p.history.latest('operating_income'),
        lambda t: t.history.latest('operating_income'),
        True,
    ),
    'EV/EBITDA': (
        lambda p: p.enterprise_value() / _ebitda(p),
        lambda t: _ebitda(t),
        True,
    ),
}
_EQUITY_ONLY = ('P/E', 'P/B')


def _ebitda(inputs: ValuationInputs) -> Optional[float]:
    ebit = inputs.history.latest('operating_income')
    da   = inputs.history.latest('depreciation')
    return ebit + da if ebit is not None and da is not None else None


def _safe(fn: Callable, arg) -> Optional[float]:
    """Evaluates a multiple/metric; None if data is missing, zero or negative."""
    try:
        v = fn(arg)
    except (TypeError, ZeroDivisionError):
        return None
    return v if v is not None and v > 0 else None


class TradingMultiples(ValuationModel):

    NAME = "Trading Multiples (peer median)"

    def __init__(self, inputs: ValuationInputs, peers: dict[str, float], peer_inputs: Optional[list[ValuationInputs]] = None):
        """
        peers:        ticker → current share price
        peer_inputs:  optional pre-built peer inputs (skips SEC fetches — used by tests)
        """
        super().__init__(inputs)
        self.peers        = peers
        self._peer_inputs = peer_inputs

    def load_peers(self) -> tuple[list[ValuationInputs], list[str]]:
        """Builds the latest fiscal year for each peer. Returns (peer inputs, warnings)."""
        if self._peer_inputs is not None:
            return self._peer_inputs, []

        loaded, warnings = [], []
        for ticker, price in self.peers.items():
            cik = TickerDB.get_cik(ticker)
            if cik is None:
                warnings.append(f"Peer {ticker}: ticker not found in tickers.db")
                continue
            try:
                history = FinancialHistory.build(cik, n_years=1)
            except ValueError as e:
                warnings.append(f"Peer {ticker}: {e}")
                continue
            loaded.append(ValuationInputs(ticker=ticker, cik=cik, history=history, price=price))
        self._peer_inputs = loaded
        return loaded, warnings

    def value(self) -> ValuationResult:
        i = self.inputs
        if not self.peers and not self._peer_inputs:
            return self._not_applicable("No peers given — pass peers={'TICKER': price, ...}")

        peers, warnings = self.load_peers()
        if not peers:
            return self._not_applicable("No peer data could be loaded")

        names = _EQUITY_ONLY if i.is_financial() else tuple(_MULTIPLES)

        peer_table = {p.ticker: {n: _safe(_MULTIPLES[n][0], p) for n in names} for p in peers}
        medians, implied = {}, {}
        for name in names:
            values = [row[name] for row in peer_table.values() if row[name] is not None]
            target_metric = _safe(_MULTIPLES[name][1], i)
            if not values or target_metric is None:
                continue
            medians[name] = median(values)
            amount = medians[name] * target_metric
            equity = self.equity_from_enterprise(amount) if _MULTIPLES[name][2] else amount
            implied[name] = self.per_share(equity)

        implied = {k: v for k, v in implied.items() if v is not None}
        if not implied:
            return self._not_applicable("No multiple could be applied (missing or negative metrics)")
        if len(peers) < 3:
            warnings.append(f"Only {len(peers)} peer(s) — medians are not robust; use 3–8 comparable companies")

        value = median(implied.values())
        return self._result(
            value,
            equity_value = value * i.shares_outstanding,
            assumptions  = {f"median_{k}": v for k, v in medians.items()},
            details = {
                'peer_multiples':      peer_table,
                'median_multiples':    medians,
                'implied_per_share':   implied,
            },
            warnings = warnings,
        )

    def summarize(self) -> None:
        result = self.value()
        result.summarize()
        if not result.applicable:
            return
        d = result.details
        names = list(d['median_multiples'])
        print(f"\n  Peer multiples")
        print(f"  {'-'*56}")
        print(f"       {'Ticker':<8}" + ''.join(f"{n:>11}" for n in names))
        for ticker, row in d['peer_multiples'].items():
            print(f"       {ticker:<8}" + ''.join(f"{row.get(n):>11.1f}" if row.get(n) is not None else f"{'—':>11}" for n in names))
        print(f"       {'Median':<8}" + ''.join(f"{d['median_multiples'][n]:>11.1f}" for n in names))
        implied = d['implied_per_share']
        print(f"       {'Implied':<8}" + ''.join(f"{implied[n]:>11,.2f}" if n in implied else f"{'—':>11}" for n in names))
        print(f"{'='*60}")
