#!/usr/bin/env python3
"""
Description: Shared inputs and outputs for every valuation model.

    FinancialHistory  → several fiscal years of statement data, as named metric series
    ValuationInputs   → history + market data + assumptions handed to a model
    ValuationResult   → what every model returns (value per share + how it got there)

Layer responsibilities:
  financial_statements/      → builds one statement for one period
  valuation_models/inputs.py → stacks FY statements into time series for the models
  valuation_models/*.py      → turn ValuationInputs into a ValuationResult

Models never call the SEC directly; they only read named metrics from
FinancialHistory. That keeps them testable offline with
FinancialHistory.from_series(...) and hand-entered numbers.

Usage:
    history = FinancialHistory.build(cik="320193", n_years=5)
    inputs  = ValuationInputs(ticker="AAPL", cik="320193", history=history, price=250.0)
    result  = DiscountedCashFlow(inputs).value()
    print(result)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from data_sources.sec import SecData
from financial_statements import Period
from financial_statements.balance_sheet import BalanceSheet
from financial_statements.cash_flow_statement import CashFlowStatement
from financial_statements.income_statement import IncomeStatement


_CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'config.json')


def load_valuation_config() -> dict:
    """Valuation defaults from config.json → 'valuation'. Returns {} if unavailable."""
    try:
        with open(_CONFIG_FILE, 'r') as f:
            return json.load(f).get('valuation', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ----------------------------------------------------------------------
# FinancialHistory — fiscal-year time series
# ----------------------------------------------------------------------

# metric name → (statement, section, line) in taxonomies_and_concepts.json
_METRICS: dict[str, tuple[str, str, str]] = {
    # Income statement
    'revenue':                    ('inc', 'revenue',                'total_revenue'),
    'gross_profit':               ('inc', 'cost_of_revenue',        'gross_profit'),
    'operating_income':           ('inc', 'operating_expenses',     'operating_income'),
    'interest_expense':           ('inc', 'non_operating',          'interest_expense'),
    'pretax_income':              ('inc', 'non_operating',          'income_before_tax'),
    'income_tax':                 ('inc', 'taxes_and_net_income',   'income_tax_expense'),
    'net_income':                 ('inc', 'taxes_and_net_income',   'net_income'),
    'eps_diluted':                ('inc', 'taxes_and_net_income',   'eps_diluted'),
    'shares_basic':               ('inc', 'taxes_and_net_income',   'shares_basic'),
    'shares_diluted':             ('inc', 'taxes_and_net_income',   'shares_diluted'),
    # Cash flow statement
    'depreciation':               ('cf',  'operating_activities',   'depreciation_amortization'),
    'sbc':                        ('cf',  'operating_activities',   'stock_based_compensation'),
    'operating_cf':               ('cf',  'operating_activities',   'operating_cf'),
    'capex':                      ('cf',  'investing_activities',   'capex'),
    'dividends_paid':             ('cf',  'financing_activities',   'dividends_paid'),
    'share_repurchases':          ('cf',  'financing_activities',   'share_repurchases'),
    # Balance sheet
    'cash':                       ('bs',  'current_assets',         'cash_and_equivalents'),
    'short_term_investments':     ('bs',  'current_assets',         'short_term_investments'),
    'accounts_receivable':        ('bs',  'current_assets',         'accounts_receivable'),
    'inventory':                  ('bs',  'current_assets',         'inventory'),
    'current_assets':             ('bs',  'current_assets',         'total_current_assets'),
    'ppe_net':                    ('bs',  'noncurrent_assets',      'ppe_net'),
    'operating_lease_rou':        ('bs',  'noncurrent_assets',      'operating_lease_rou'),
    'goodwill':                   ('bs',  'noncurrent_assets',      'goodwill'),
    'intangible_assets':          ('bs',  'noncurrent_assets',      'intangible_assets'),
    'long_term_investments':      ('bs',  'noncurrent_assets',      'long_term_investments'),
    'deferred_tax_assets':        ('bs',  'noncurrent_assets',      'deferred_tax_assets'),
    'total_assets':               ('bs',  'noncurrent_assets',      'total_assets'),
    'current_liabilities':        ('bs',  'current_liabilities',    'total_current_liabilities'),
    'short_term_debt':            ('bs',  'current_liabilities',    'short_term_debt'),
    'current_portion_ltd':        ('bs',  'current_liabilities',    'current_portion_ltd'),
    'operating_lease_current':    ('bs',  'current_liabilities',    'operating_lease_current'),
    'long_term_debt':             ('bs',  'noncurrent_liabilities', 'long_term_debt'),
    'operating_lease_noncurrent': ('bs',  'noncurrent_liabilities', 'operating_lease_noncurrent'),
    'total_liabilities':          ('bs',  'noncurrent_liabilities', 'total_liabilities'),
    'total_equity':               ('bs',  'stockholders_equity',    'total_stockholders_equity'),
}

# Filed as payments (positive outflows) — always use the magnitude
_ABSOLUTE = {'capex', 'dividends_paid', 'share_repurchases'}

# Long-term investment tags that hold debt securities (bonds, Treasuries, agency
# paper). These are liquid, so the equity bridge counts them as cash. Any other
# tag in the long_term_investments chain (LongTermInvestments, equity securities
# without a market price, investments + receivables) is treated as strategic or
# illiquid and left out. Per-ticker overrides live in config.json.
CASH_LIKE_INVESTMENT_TAGS = {
    'MarketableSecuritiesNoncurrent',
    'AvailableForSaleSecuritiesNoncurrent',
    'AvailableForSaleSecuritiesDebtSecuritiesNoncurrent',
    'DebtSecuritiesAvailableForSaleNoncurrent',
    'HeldToMaturitySecuritiesNoncurrent',
}


class FinancialHistory:
    """
    Fiscal-year metric series for one company, oldest year first.

    Every series is aligned with self.years and may contain None where a
    line item was not filed. Missing years (no 10-K) are dropped at build time.
    """

    METRICS = tuple(_METRICS)

    def __init__(self, cik: str, years: list[int], data: dict[str, list[Optional[float]]],
                 statements: Optional[dict] = None, tags: Optional[dict[str, list[Optional[str]]]] = None):
        self.cik        = cik
        self.years      = years
        self._data      = data
        self._tags      = tags or {}        # metric → XBRL tag that supplied each year's value
        self.statements = statements or {}  # year → {'bs','inc','cf'} for drill-down / reporting

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @staticmethod
    def latest_fiscal_year(cik: str) -> Optional[int]:
        """Calendar year in which the most recent 10-K fiscal year ended."""
        data  = SecData.get_concept(cik=cik, taxonomy='us-gaap', concept='Assets')
        ends  = [e['end'] for e in data.get('units', {}).get('USD', []) if e.get('form') == '10-K' and e.get('end')]
        return int(max(ends)[:4]) if ends else None

    @classmethod
    def build(cls, cik: str, last_year: Optional[int] = None, n_years: int = 5) -> 'FinancialHistory':
        """
        Builds FY statements for n_years ending at last_year (default: latest 10-K).

        Cheap after the first year: SecData.get_concept is cached per concept,
        and each concept payload already contains every historical period.
        """
        last_year = last_year or cls.latest_fiscal_year(cik)
        if last_year is None:
            raise ValueError(f"No 10-K filings found for CIK {cik}")

        years: list[int] = []
        data: dict[str, list[Optional[float]]] = {m: [] for m in _METRICS}
        tags: dict[str, list[Optional[str]]]   = {m: [] for m in _METRICS}
        statements: dict[int, dict] = {}

        for year in range(last_year - n_years + 1, last_year + 1):
            stmts = {
                'bs':  BalanceSheet(cik, year, Period.FY).build(),
                'inc': IncomeStatement(cik, year, Period.FY).build(),
                'cf':  CashFlowStatement(cik, year, Period.FY).build(),
            }
            # Skip years with no usable filing (e.g. before the company went public)
            if stmts['inc'].get_total_revenue() is None and stmts['bs'].get_total_assets() is None:
                continue

            years.append(year)
            statements[year] = stmts
            for metric, (stmt, section, line) in _METRICS.items():
                val = stmts[stmt].get_line_item(section, line)
                data[metric].append(abs(val) if val is not None and metric in _ABSOLUTE else val)
                tags[metric].append(stmts[stmt].data.get(section, {}).get(line, {}).get('tag_used') if val is not None else None)

        return cls(cik, years, data, statements, tags)

    @classmethod
    def from_series(cls, years: list[int], series: dict[str, list[Optional[float]]], cik: str = 'manual',
                    tags: Optional[dict[str, list[Optional[str]]]] = None) -> 'FinancialHistory':
        """Builds a history from plain lists — for tests and what-if analysis."""
        data = {m: list(series.get(m, [None] * len(years))) for m in _METRICS}
        for m, vals in data.items():
            if len(vals) != len(years):
                raise ValueError(f"Series '{m}' has {len(vals)} values for {len(years)} years")
        return cls(cik, years, data, tags=tags)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.years)

    def series(self, metric: str) -> list[Optional[float]]:
        return self._data[metric]

    def latest(self, metric: str) -> Optional[float]:
        """Most recent non-missing value."""
        return next((v for v in reversed(self._data[metric]) if v is not None), None)

    def latest_tag(self, metric: str) -> Optional[str]:
        """XBRL tag behind latest(metric) — None for hand-built histories."""
        tags = self._tags.get(metric) or [None] * len(self.years)
        return next((t for v, t in zip(reversed(self._data[metric]), reversed(tags)) if v is not None), None)

    def value_at(self, metric: str, offset: int = 0) -> Optional[float]:
        """Value `offset` years before the latest year (0 = latest). No fallback."""
        vals = self._data[metric]
        return vals[-1 - offset] if offset < len(vals) else None

    def average(self, metric: str, n: Optional[int] = None) -> Optional[float]:
        """Average over the last n years (default all), ignoring missing values."""
        vals = [v for v in self._data[metric][-(n or len(self.years)):] if v is not None]
        return sum(vals) / len(vals) if vals else None

    def ratio_series(self, numerator: str, denominator: str) -> list[Optional[float]]:
        """Year-by-year numerator / denominator, None where either is missing or zero."""
        return [
            n / d if n is not None and d else None
            for n, d in zip(self._data[numerator], self._data[denominator])
        ]

    def average_ratio(self, numerator: str, denominator: str) -> Optional[float]:
        vals = [v for v in self.ratio_series(numerator, denominator) if v is not None]
        return sum(vals) / len(vals) if vals else None

    def cagr(self, metric: str) -> Optional[float]:
        """Compound annual growth between the first and last non-missing positive values."""
        return _cagr(self.years, self._data[metric])

    def split_detected(self) -> bool:
        """
        True if diluted shares jump by more than 40% between consecutive years.
        Older filings are not restated for later stock splits, so per-share
        series (EPS, DPS) across a split are not comparable.
        """
        shares = [s for s in self._data['shares_diluted'] if s]
        return any(b / a > 1.4 or b / a < 0.7 for a, b in zip(shares, shares[1:]))

    def per_share_cagr(self, metric: str) -> Optional[float]:
        """
        Growth of metric / diluted shares (e.g. net income → EPS growth,
        dividends paid → DPS growth). Falls back to the total-amount CAGR
        when a stock split makes the per-share series unreliable.
        """
        if self.split_detected():
            return self.cagr(metric)
        per_share = [m / s if m is not None and s else None
                     for m, s in zip(self._data[metric], self._data['shares_diluted'])]
        return _cagr(self.years, per_share)


def _cagr(years: list[int], values: list[Optional[float]]) -> Optional[float]:
    """Compound annual growth between the first and last non-missing values (both must be positive)."""
    points = [(y, v) for y, v in zip(years, values) if v is not None]
    if len(points) < 2:
        return None
    (y0, v0), (y1, v1) = points[0], points[-1]
    if v0 <= 0 or v1 <= 0 or y1 == y0:
        return None
    return (v1 / v0) ** (1 / (y1 - y0)) - 1


# ----------------------------------------------------------------------
# ValuationInputs — everything a model needs
# ----------------------------------------------------------------------

@dataclass
class ValuationInputs:
    """
    Inputs shared by every valuation model.

    Market fields (price, beta, risk_free_rate, equity_risk_premium) come
    from config.json defaults until a market data source exists — pass real
    values explicitly when you have them. Every default that gets used is
    recorded in `defaults_used` so results can flag it.
    """
    ticker:  str
    cik:     str
    history: FinancialHistory

    price:               Optional[float] = None   # current share price
    shares_outstanding:  Optional[float] = None   # default: see default_shares()
    shares_source:       str             = 'given'
    sic:                 Optional[str]   = None   # default: looked up from SEC submissions
    beta:                Optional[float] = None
    risk_free_rate:      Optional[float] = None
    equity_risk_premium: Optional[float] = None

    config:        dict      = field(default_factory=load_valuation_config)
    defaults_used: list[str] = field(default_factory=list)

    def __post_init__(self):
        for name in ('beta', 'risk_free_rate', 'equity_risk_premium'):
            if getattr(self, name) is None:
                setattr(self, name, self.config.get(name))
                self.defaults_used.append(name)

        if self.shares_outstanding is None:
            self.shares_outstanding, self.shares_source = self.default_shares()

        if self.sic is None and self.cik != 'manual':
            self.sic = str(SecData.get_submissions(self.cik).get('sic') or '') or None

    # ------------------------------------------------------------------
    # Share count
    # ------------------------------------------------------------------
    def default_shares(self) -> tuple[Optional[float], str]:
        """
        Best available share count for per-share values, in order:

          1. Cover-page shares outstanding (dei:EntityCommonStockSharesOutstanding)
             from the most recent 10-K/10-Q, plus option/RSU dilution
             (diluted − basic weighted shares in the latest fiscal year).
             This is the newest count — weighted averages lag buybacks/issuance.
          2. Latest fiscal year weighted-average diluted shares.

        Companies with several share classes (e.g. Alphabet) report the cover
        count per class only, so they fall through to option 2.
        """
        weighted = self.history.latest('shares_diluted')
        if self.cik == 'manual':
            return weighted, 'weighted diluted (FY)'

        cover = SecData.get_concept(cik=self.cik, taxonomy='dei', concept='EntityCommonStockSharesOutstanding')
        entries = [e for e in cover.get('units', {}).get('shares', [])
                   if e.get('form') in ('10-K', '10-Q', '10-K/A', '10-Q/A') and e.get('val')]
        if not entries:
            return weighted, 'weighted diluted (FY)'

        latest_end = max(e['end'] for e in entries)
        same_date  = [e for e in entries if e['end'] == latest_end]
        if len({e['val'] for e in same_date}) > 1:
            return weighted, 'weighted diluted (FY) — multiple share classes'
        outstanding = max(same_date, key=lambda e: e.get('filed', ''))['val']

        diluted, basic = self.history.value_at('shares_diluted'), self.history.value_at('shares_basic')
        dilution = max(diluted - basic, 0.0) if diluted and basic else 0.0
        return outstanding + dilution, f"cover page {latest_end} + dilution"

    # ------------------------------------------------------------------
    # Assumptions
    # ------------------------------------------------------------------
    def assumption(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def tax_rate(self) -> float:
        """
        Average effective tax rate over the history, bounded to [0, 35%].
        Falls back to the marginal rate when the history has no usable data.
        """
        marginal = self.assumption('marginal_tax_rate', 0.21)
        pairs = zip(self.history.series('income_tax'), self.history.series('pretax_income'))
        rates = [t / p for t, p in pairs if t is not None and p and p > 0]
        if not rates:
            return marginal
        return min(max(sum(rates) / len(rates), 0.0), 0.35)

    # ------------------------------------------------------------------
    # Capital structure (latest balance sheet)
    # ------------------------------------------------------------------
    def total_debt(self, offset: int = 0) -> float:
        """
        Interest-bearing debt at the balance sheet `offset` years back (0 = latest).
        Operating leases are included by default (debt-like fixed obligations since ASC 842).
        """
        parts = ['short_term_debt', 'current_portion_ltd', 'long_term_debt']
        if self.assumption('include_operating_leases_in_debt', True):
            parts += ['operating_lease_current', 'operating_lease_noncurrent']
        return sum(self.history.value_at(p, offset) or 0.0 for p in parts)

    def long_term_investments_in_cash(self) -> tuple[float, str]:
        """
        Long-term investments counted as cash in the equity bridge, and why.

          1. Per-ticker override   config → long_term_investments_overrides {"AAPL": true}
          2. Global setting        config → long_term_investments_in_cash  true / false
          3. "auto" (default)      decided by the XBRL tag the company filed:
                                   debt-security tags count (CASH_LIKE_INVESTMENT_TAGS),
                                   anything else is treated as strategic and excluded
        """
        amount = self.history.latest('long_term_investments')
        if not amount:
            return 0.0, 'none reported'

        override = self.assumption('long_term_investments_overrides', {}).get(self.ticker.upper())
        if override is not None:
            return (amount, 'included (ticker override)') if override else (0.0, 'excluded (ticker override)')

        mode = self.assumption('long_term_investments_in_cash', 'auto')
        if mode is True:
            return amount, 'included (config)'
        if mode is False:
            return 0.0, 'excluded (config)'

        tag = self.history.latest_tag('long_term_investments')
        if tag in CASH_LIKE_INVESTMENT_TAGS:
            return amount, f'included: {tag} (debt securities)'
        return 0.0, f"excluded: {tag or 'unknown tag'} (strategic / illiquid)"

    def cash_and_investments(self) -> float:
        """Cash + short-term investments + any long-term investments that count as cash."""
        cash = sum(self.history.latest(p) or 0.0 for p in ('cash', 'short_term_investments'))
        return cash + self.long_term_investments_in_cash()[0]

    def net_debt(self) -> float:
        return self.total_debt() - self.cash_and_investments()

    def market_cap(self) -> Optional[float]:
        if self.price is None or not self.shares_outstanding:
            return None
        return self.price * self.shares_outstanding

    def equity_bridge(self, enterprise_value: float) -> list[tuple[str, float, str]]:
        """
        Line-by-line enterprise → equity value as (label, amount, note), for display.
        The last row is the equity value.
        """
        lti, reason = self.long_term_investments_in_cash()
        leases = 'incl. operating leases' if self.assumption('include_operating_leases_in_debt', True) else ''
        rows = [
            ('Enterprise value',         enterprise_value,                                         ''),
            ('− Debt',                   -self.total_debt(),                                       leases),
            ('+ Cash and equivalents',   self.history.latest('cash') or 0.0,                      ''),
            ('+ Short-term investments', self.history.latest('short_term_investments') or 0.0,     ''),
            ('+ Long-term investments',  lti,                                                      reason),
        ]
        rows.append(('= Equity value', sum(v for _, v, _ in rows), ''))
        return rows

    def total_liabilities(self) -> Optional[float]:
        """Latest total liabilities; derived as assets − equity when the total is not tagged."""
        h = self.history
        liabilities = h.value_at('total_liabilities', 0)
        if liabilities is not None:
            return liabilities
        assets, equity = h.value_at('total_assets', 0), h.value_at('total_equity', 0)
        return assets - equity if assets is not None and equity is not None else None

    def enterprise_value(self) -> Optional[float]:
        mc = self.market_cap()
        return mc + self.net_debt() if mc is not None else None

    # ------------------------------------------------------------------
    # Applicability
    # ------------------------------------------------------------------
    def is_financial(self) -> bool:
        """
        Banks, insurers, brokers and REITs (SIC 6000–6799). Their debt is raw
        material rather than financing, so FCFF / EV-based models do not apply.
        """
        return self.sic is not None and self.sic.isdigit() and 6000 <= int(self.sic) <= 6799


# ----------------------------------------------------------------------
# ValuationResult — what every model returns
# ----------------------------------------------------------------------

@dataclass
class ValuationResult:
    model:            str
    value_per_share:  Optional[float]
    price:            Optional[float] = None
    equity_value:     Optional[float] = None
    enterprise_value: Optional[float] = None
    applicable:       bool            = True
    assumptions:      dict            = field(default_factory=dict)
    details:          dict            = field(default_factory=dict)   # projections, grids, peer tables
    warnings:         list[str]       = field(default_factory=list)

    @classmethod
    def not_applicable(cls, model: str, reason: str, price: Optional[float] = None) -> 'ValuationResult':
        return cls(model=model, value_per_share=None, price=price, applicable=False, warnings=[reason])

    @property
    def upside(self) -> Optional[float]:
        """Value / price − 1. Positive means the model says the stock is cheap."""
        if self.value_per_share is None or not self.price:
            return None
        return self.value_per_share / self.price - 1

    @property
    def margin_of_safety(self) -> Optional[float]:
        """1 − price / value: the discount to intrinsic value you are buying at."""
        if not self.value_per_share or self.price is None or self.value_per_share <= 0:
            return None
        return 1 - self.price / self.value_per_share

    def __str__(self) -> str:
        if not self.applicable:
            return f"{self.model:<32} {'N/A':>12}   ({'; '.join(self.warnings)})"
        val = f"${self.value_per_share:,.2f}" if self.value_per_share is not None else 'N/A'
        up  = f"{self.upside:+.1%}" if self.upside is not None else ''
        return f"{self.model:<32} {val:>12}   {up}"

    def summarize(self) -> None:
        print(f"\n{'='*60}")
        print(f"{self.model}")
        print(f"{'='*60}")
        print(f"  Value per share:   {f'${self.value_per_share:,.2f}' if self.value_per_share is not None else 'N/A'}")
        if self.price is not None:
            print(f"  Price:             ${self.price:,.2f}")
        if self.upside is not None:
            print(f"  Upside:            {self.upside:+.1%}")
        if self.margin_of_safety is not None and self.margin_of_safety > 0:
            # Only meaningful when price is below value; when above, upside already shows the gap
            print(f"  Margin of safety:  {self.margin_of_safety:.1%}")
        if self.enterprise_value is not None:
            print(f"  Enterprise value:  ${self.enterprise_value:,.0f}")
        if self.equity_value is not None:
            print(f"  Equity value:      ${self.equity_value:,.0f}")
        if self.assumptions:
            print(f"\n  Assumptions")
            print(f"  {'-'*50}")
            for k, v in self.assumptions.items():
                print(f"       {k:<36} {_fmt_assumption(k, v)}")
        if self.warnings:
            print(f"\n  ⚠  Warnings")
            for w in self.warnings:
                print(f"       - {w}")
        print(f"{'='*60}")


_PERCENT_HINTS = ('rate', 'growth', 'margin', 'premium', 'wacc', 'cost', 'weight', 'spread', 'yield', 'payout', 'roe')


def _fmt_assumption(key: str, v: Any) -> str:
    """Rates print as percentages, money as $ with separators, everything else as-is."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if any(h in key for h in _PERCENT_HINTS):
        return f"{v:.2%}"
    if 'shares' in key:
        return f"{v:,.0f}"
    if abs(v) >= 1e6:
        return f"${v:,.0f}"
    return f"{v:,}" if isinstance(v, int) else f"{v:,.2f}"
