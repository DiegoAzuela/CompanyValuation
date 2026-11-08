"""
Offline tests for valuation_models — every expected value is a hand calculation.
Run:  pytest -q
"""
import math

import pytest

from financial_statements import Period, previous_period
from financial_statements.income_statement import ReconciliationResult
from valuation_models import ValuationModel
from valuation_models.inputs import FinancialHistory, ValuationInputs
from valuation_models.wacc import WACC
from valuation_models.dcf_valuation import DiscountedCashFlow
from valuation_models.earning_power import EarningsPowerValue
from valuation_models.earnings_capitalization import AverageEarningsCapitalization
from valuation_models.peter_lynch_fairvalue import PeterLynchFairValue
from valuation_models.dividend_discount import DividendDiscountModel
from valuation_models.trading_multiples import TradingMultiples
from valuation_models.asset_value import NetCurrentAssetValue, LiquidationValue
from valuation_models.book_value import JustifiedPriceToBook, GrahamNumber


CONFIG = {
    'risk_free_rate': 0.04, 'equity_risk_premium': 0.05, 'beta': 1.2,
    'marginal_tax_rate': 0.21, 'default_debt_weight': 0.10, 'default_credit_spread': 0.01,
    'synthetic_rating_spreads': [[8.5, 'AAA', 0.0059], [3.0, 'A-', 0.0121], [-1e9, 'D', 0.19]],
    'projection_years': 1, 'terminal_growth': 0.02, 'max_initial_growth': 0.15,
    'sbc_as_expense': True, 'include_operating_leases_in_debt': True,
    'long_term_investments_in_cash': 'auto', 'long_term_investments_overrides': {},
    'synthetic_rating_spreads_as_of': '2026-01', 'spreads_max_age_months': 15, 'reverse_dcf_years': 10,
    'avg_earnings_multiple': 15, 'avg_earnings_years': 3, 'lynch_max_growth': 25, 'ddm_max_growth': 0.04,
    'liquidation_recovery': {'cash': 1.0, 'accounts_receivable': 0.8, 'inventory': 0.67, 'ppe_net': 0.15,
                             'other_assets': 0.15, 'goodwill': 0.0},
}

YEARS = [2021, 2022, 2023]


def make_inputs(series: dict, price=None, sic=None, years=YEARS, tags=None, **overrides) -> ValuationInputs:
    base = {'shares_diluted': [100.0] * len(years)}
    history = FinancialHistory.from_series(years, {**base, **series}, tags=tags)
    return ValuationInputs(ticker='TEST', cik='manual', history=history, price=price, sic=sic,
                           config={**CONFIG, **overrides})


# ----------------------------------------------------------------------
# Statement helpers
# ----------------------------------------------------------------------
def test_previous_period():
    assert previous_period(2025, Period.Q2) == (2025, Period.Q1)
    assert previous_period(2025, Period.Q4) == (2025, Period.Q3)
    assert previous_period(2025, Period.Q1) == (2024, Period.Q4)
    assert previous_period(2025, Period.FY) == (2024, Period.Q4)


def test_reconciliation_result_tolerance():
    ok  = ReconciliationResult.compare(net_income=100.0, explained=98.0, tolerance_pct=0.03)
    bad = ReconciliationResult.compare(net_income=100.0, explained=90.0, tolerance_pct=0.03)
    assert ok.passed and ok.residual == pytest.approx(2.0)
    assert not bad.passed and bad.residual_pct == pytest.approx(0.10)


# ----------------------------------------------------------------------
# Shared math
# ----------------------------------------------------------------------
def test_present_value_end_and_mid_year():
    assert ValuationModel.present_value([110, 121], 0.10) == pytest.approx(200.0)
    assert ValuationModel.present_value([110], 0.10, mid_year=True) == pytest.approx(110 / 1.1 ** 0.5)


def test_terminal_value_and_guard():
    assert ValuationModel.terminal_value(100, 0.02, 0.10) == pytest.approx(1275.0)
    with pytest.raises(ValueError):
        ValuationModel.terminal_value(100, 0.10, 0.08)


# ----------------------------------------------------------------------
# FinancialHistory
# ----------------------------------------------------------------------
def test_history_helpers():
    h = FinancialHistory.from_series(YEARS, {'revenue': [100.0, None, 121.0], 'shares_diluted': [10.0, 10.0, 10.0]})
    assert h.cagr('revenue') == pytest.approx(0.10)
    assert h.average('revenue') == pytest.approx(110.5)
    assert h.latest('revenue') == 121.0
    assert not h.split_detected()


def test_split_detection_falls_back_to_total_growth():
    h = FinancialHistory.from_series(YEARS, {'net_income': [100.0, 110.0, 121.0], 'shares_diluted': [10.0, 40.0, 40.0]})
    assert h.split_detected()
    assert h.per_share_cagr('net_income') == pytest.approx(0.10)


# ----------------------------------------------------------------------
# WACC
# ----------------------------------------------------------------------
def test_wacc_hand_calculation():
    i = make_inputs({'operating_income': [None, None, 100.0], 'interest_expense': [None, None, 10.0],
                     'long_term_debt': [250.0] * 3}, price=10.0)
    b = WACC(i).compute()
    assert b.cost_of_equity == pytest.approx(0.04 + 1.2 * 0.05)          # 10%
    assert b.synthetic_rating == 'AAA'                                    # coverage 10x
    kd_after = (0.04 + 0.0059) * (1 - 0.21)
    assert b.debt_weight == pytest.approx(250 / (250 + 1000))             # market cap 10 × 100
    assert b.wacc == pytest.approx(0.8 * 0.10 + 0.2 * kd_after)


def test_wacc_estimates_interest_when_latest_year_missing():
    # FY2021 reports 20 interest on 400 debt (5%); later years stop tagging interest.
    # Latest debt 300 × 5% = 15 estimated interest → coverage 150 / 15 = 10x
    i = make_inputs({'operating_income': [100.0, 120.0, 150.0], 'interest_expense': [20.0, None, None],
                     'long_term_debt': [400.0, 350.0, 300.0]})
    coverage, method = WACC(i).interest_coverage()
    assert coverage == pytest.approx(10.0)
    assert method.startswith('estimated from FY2021')


def test_wacc_no_interest_ever_uses_default_spread():
    i = make_inputs({'operating_income': [100.0] * 3, 'long_term_debt': [300.0] * 3})
    b = WACC(i).compute()
    assert b.synthetic_rating == 'n/a'
    assert b.pre_tax_cost_of_debt == pytest.approx(0.04 + 0.01)


def test_wacc_without_price_uses_assumed_weight():
    i = make_inputs({'long_term_debt': [250.0] * 3})
    b = WACC(i).compute()
    assert b.debt_weight == pytest.approx(0.10)
    assert any('No share price' in w for w in b.warnings)


# ----------------------------------------------------------------------
# DCF
# ----------------------------------------------------------------------
def test_dcf_one_year_hand_calculation():
    i = make_inputs({'revenue': [1000.0] * 3})
    dcf = DiscountedCashFlow(i, wacc=0.10, initial_growth=0.02, fcff_margin=0.10, mid_year=False)
    r = dcf.value()
    # revenue 1020 → FCFF 102; TV = 102 × 1.02 / 0.08 = 1300.5; EV = (102 + 1300.5) / 1.1 = 1275
    assert r.enterprise_value == pytest.approx(1275.0)
    assert r.value_per_share == pytest.approx(12.75)


def test_dcf_historical_fcff_subtracts_sbc_and_adds_after_tax_interest():
    i = make_inputs({'revenue': [1000.0] * 3, 'operating_cf': [200.0] * 3, 'capex': [50.0] * 3,
                     'interest_expense': [10.0] * 3, 'sbc': [20.0] * 3})
    assert DiscountedCashFlow(i).historical_fcff() == pytest.approx([200 - 50 + 10 * 0.79 - 20] * 3)


def test_reverse_dcf_recovers_growth():
    # 2% for 10 years then 2% forever is the same as the 1-year base case → same price
    i = make_inputs({'revenue': [1000.0] * 3}, price=12.75)
    dcf = DiscountedCashFlow(i, wacc=0.10, initial_growth=0.02, fcff_margin=0.10, mid_year=False)
    assert dcf.value().details['implied_growth'] == pytest.approx(0.02, abs=1e-6)


def test_reverse_dcf_constant_rate_reprices_to_price():
    i = make_inputs({'revenue': [1000.0] * 3}, price=20.0)
    dcf = DiscountedCashFlow(i, wacc=0.10, initial_growth=0.02, fcff_margin=0.10, mid_year=False)
    g = dcf.value().details['implied_growth']
    assert g > 0.02
    assert dcf._run([g] * 10, 0.02, 0.10, 0.10)['value_per_share'] == pytest.approx(20.0, abs=1e-6)


# ----------------------------------------------------------------------
# Equity bridge — long-term investments by XBRL tag
# ----------------------------------------------------------------------
def _lti_inputs(tag, **overrides):
    return make_inputs({'cash': [None, None, 10.0], 'long_term_investments': [None, None, 50.0]},
                       tags={'long_term_investments': [None, None, tag]}, **overrides)


def test_debt_security_investments_count_as_cash():
    i = _lti_inputs('MarketableSecuritiesNoncurrent')
    assert i.cash_and_investments() == pytest.approx(60.0)
    assert i.equity_bridge(100.0)[-1][1] == pytest.approx(160.0)


def test_strategic_investments_excluded_unless_overridden():
    assert _lti_inputs('LongTermInvestments').cash_and_investments() == pytest.approx(10.0)
    forced = _lti_inputs('LongTermInvestments', long_term_investments_overrides={'TEST': True})
    assert forced.cash_and_investments() == pytest.approx(60.0)


def test_spread_table_staleness():
    from datetime import date
    w = WACC(make_inputs({}))
    assert w.spread_table_warning(today=date(2027, 4, 1)) is None        # 15 months
    assert '16 months old' in w.spread_table_warning(today=date(2027, 5, 1))


# ----------------------------------------------------------------------
# Balance-sheet models
# ----------------------------------------------------------------------
def test_ncav_hand_calculation():
    i = make_inputs({'current_assets': [None, None, 500.0], 'total_liabilities': [None, None, 300.0]})
    r = NetCurrentAssetValue(i).value()
    assert r.value_per_share == pytest.approx(2.0)
    assert r.details['buy_below'] == pytest.approx(4 / 3)
    no_net_net = make_inputs({'current_assets': [None, None, 100.0], 'total_liabilities': [None, None, 300.0]})
    assert not NetCurrentAssetValue(no_net_net).value().applicable


def test_liquidation_value_hand_calculation():
    i = make_inputs({'cash': [None, None, 100.0], 'accounts_receivable': [None, None, 100.0],
                     'inventory': [None, None, 90.0], 'current_assets': [None, None, 300.0],
                     'ppe_net': [None, None, 200.0], 'goodwill': [None, None, 50.0],
                     'total_assets': [None, None, 550.0], 'total_liabilities': [None, None, 150.0]})
    # 100 + 80 + 60.3 + other current 10 × 15% + PP&E 200 × 15% + goodwill 0 = 271.8 − 150 = 121.8
    r = LiquidationValue(i).value()
    assert r.equity_value == pytest.approx(121.8)
    assert r.value_per_share == pytest.approx(1.218)


def test_total_liabilities_derived_from_assets_minus_equity():
    i = make_inputs({'total_assets': [None, None, 500.0], 'total_equity': [None, None, 200.0]})
    assert i.total_liabilities() == pytest.approx(300.0)


def test_justified_price_to_book():
    i = make_inputs({'net_income': [20.0] * 3, 'total_equity': [100.0] * 3})
    r = JustifiedPriceToBook(i, cost_of_equity=0.10, growth=0.02).value()
    # ROE 20% → P/B = (0.20 − 0.02) / (0.10 − 0.02) = 2.25 × BVPS 1.00
    assert r.assumptions['justified_pb'] == pytest.approx(2.25)
    assert r.value_per_share == pytest.approx(2.25)


def test_graham_number():
    i = make_inputs({'net_income': [None, None, 100.0], 'total_equity': [None, None, 1000.0]})
    # EPS 1.00, BVPS 10.00 → √(22.5 × 1 × 10) = 15
    assert GrahamNumber(i).value().value_per_share == pytest.approx(15.0)


def test_dcf_not_applicable_to_banks_and_caps_terminal_growth():
    assert not DiscountedCashFlow(make_inputs({'revenue': [1000.0] * 3}, sic='6022')).value().applicable
    r = DiscountedCashFlow(make_inputs({'revenue': [1000.0] * 3}), wacc=0.10, fcff_margin=0.1, terminal_growth=0.06).value()
    assert r.assumptions['terminal_growth'] == pytest.approx(0.04)


# ----------------------------------------------------------------------
# Earnings / dividend models
# ----------------------------------------------------------------------
def test_epv_hand_calculation():
    i = make_inputs({'revenue': [1000.0] * 3, 'operating_income': [200.0] * 3, 'depreciation': [50.0] * 3,
                     'capex': [60.0] * 3, 'ppe_net': [500.0] * 3,
                     'income_tax': [38.0] * 3, 'pretax_income': [190.0] * 3})
    r = EarningsPowerValue(i, wacc=0.10).value()
    # no growth → maintenance capex = capex; adj EBIT = 200 + 50 − 60 = 190; NOPAT = 152; / 10% = 1520
    assert r.value_per_share == pytest.approx(15.20)


def test_average_earnings_capitalization():
    r = AverageEarningsCapitalization(make_inputs({'net_income': [90.0, 100.0, 110.0]})).value()
    assert r.value_per_share == pytest.approx(15 * 100 / 100)


def test_peter_lynch_fair_value():
    r = PeterLynchFairValue(make_inputs({'net_income': [100.0, 110.0, 121.0]})).value()
    # EPS 1.21, growth 10% → fair P/E 10
    assert r.value_per_share == pytest.approx(12.10)
    assert not PeterLynchFairValue(make_inputs({'net_income': [121.0, 110.0, 100.0]})).value().applicable


def test_dividend_discount_model():
    i = make_inputs({'dividends_paid': [100.0] * 3, 'net_income': [200.0] * 3})
    r = DividendDiscountModel(i, cost_of_equity=0.08, growth=0.03).value()
    assert r.value_per_share == pytest.approx(1.03 / 0.05)
    assert r.details['dividend_record']['payout_ratio'] == pytest.approx(0.5)
    assert not DividendDiscountModel(make_inputs({'net_income': [1.0] * 3})).value().applicable


# ----------------------------------------------------------------------
# Trading multiples
# ----------------------------------------------------------------------
def test_trading_multiples_median():
    target = make_inputs({'net_income': [None, None, 100.0]})
    peers = []
    for ticker, price in (('A', 10.0), ('B', 20.0), ('C', 30.0)):
        h = FinancialHistory.from_series([2023], {'net_income': [100.0], 'shares_diluted': [100.0]})
        peers.append(ValuationInputs(ticker=ticker, cik='manual', history=h, price=price, config=CONFIG))
    r = TradingMultiples(target, peers={}, peer_inputs=peers).value()
    # peer P/Es 10, 20, 30 → median 20 × target EPS 1.00
    assert r.details['median_multiples']['P/E'] == pytest.approx(20.0)
    assert r.value_per_share == pytest.approx(20.0)
    assert math.isclose(r.details['implied_per_share']['P/E'], 20.0)
