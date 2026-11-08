from financial_statements.balance_sheet import BalanceSheet
from financial_statements.income_statement import IncomeStatement
from financial_statements.cash_flow_statement import CashFlowStatement
from financial_statements import FinancialStatement, Period, previous_period
from db.database import TickerDatabase 
from data_sources.sec import SecData
from db.tickers import TickerDB
from valuation_models.inputs import FinancialHistory, ValuationInputs, load_valuation_config
from valuation_models.wacc import WACC, PLACEHOLDER_WARNING
from valuation_models.dcf_valuation import DiscountedCashFlow
from valuation_models.earning_power import EarningsPowerValue
from valuation_models.earnings_capitalization import AverageEarningsCapitalization
from valuation_models.peter_lynch_fairvalue import PeterLynchFairValue
from valuation_models.dividend_discount import DividendDiscountModel
from valuation_models.trading_multiples import TradingMultiples
from valuation_models.asset_value import NetCurrentAssetValue, LiquidationValue
from valuation_models.book_value import JustifiedPriceToBook, GrahamNumber
from dotenv import load_dotenv
import os
import sys

# Windows defaults to cp1252 when output is redirected to a file/pipe, which
# cannot encode the box-drawing and ✓/⚠ characters used in the summaries
sys.stdout.reconfigure(encoding='utf-8')

TickerDatabase.init_db()
SecData.seed_db()  # only re-downloads when the local list is older than 7 days

# Latest filing: FY2026 10-K (fiscal year ended 2026-09-26, filed 2026-11-03)
load_dotenv()
taxonomy = "us-gaap"
TICKER = "AAPL"
CIK  = "320193"  # Apple
YEAR = 2026
PERIOD = Period.FY

# ── Valuation inputs ──────────────────────────────────────────────────
# No market data source yet: set the current price and peer prices by hand.
# With PRICE = None, models still run but upside / margin of safety are N/A
# and the WACC falls back to an assumed debt weight.
PRICE = None                  # e.g. 250.00
PEERS = {}                    # e.g. {"MSFT": 510.00, "GOOGL": 245.00, "META": 720.00}

if __name__ == "__main__":
    cik_from_db = TickerDB.get_cik(TICKER)

    # Display the summary of what will be evaluated
    print(f"\n{'='*60}")
    print(f"{'='*60}")
    print(f"Will review information for {TICKER}:{cik_from_db} in year {YEAR}")
    print(f"{'='*60}")
    print(f"{'='*60}\n")

    def fmt(val, spec, prefix='', suffix=''):
        return f"{prefix}{val:{spec}}{suffix}" if val is not None else 'N/A'

    # ── Balance Sheet ─────────────────────────────────────────────────
    bs = BalanceSheet(CIK, YEAR, PERIOD).build()
    bs.summarize()
    print(f"Balanced:           {bs.is_balanced()}")
    print(f"Working Capital:    {fmt(bs.working_capital(), ',.0f')}")
    print(f"Current Ratio:      {fmt(bs.current_ratio(), '.2f', suffix='x')}")
    print(f"Debt-to-Equity:     {fmt(bs.debt_to_equity(), '.2f', suffix='x')}")

    # ── Income Statement ──────────────────────────────────────────────
    inc = IncomeStatement(CIK, YEAR, PERIOD).build()
    inc.summarize()
    print(f"Coherence:          {inc.is_coherent()}")
    print(f"NI > OI flag:       {inc.NetIncome_to_OperatingIncome()}")

    # ── Cash Flow Statement ───────────────────────────────────────────
    cf = CashFlowStatement(CIK, YEAR, PERIOD).build()
    cf.summarize()
    print(f"Coherence:          {cf.is_coherent()}")
    print(f"Free Cash Flow:     {fmt(cf.free_cash_flow(), ',.0f')}")
    print(f"Ending cash == BS:  {cf.ending_cash_check(bs)}")

    # ── Cross-statement checks ────────────────────────────────────────
    print(f"\n── Cross-statement ──────────────────────────────────")
    print(f"Cash conversion:    {fmt(inc.fall_to_sales(cf), '.2%')}")
    print(f"Op CF / Net Income: {fmt(cf.operating_cf_to_net_income(inc), '.2f', suffix='x')}")

    # reconciliation compares against the balance sheet that opens this period
    # (prior quarter for Q2–Q4, prior fiscal year end for Q1 / FY)
    bs_prior = BalanceSheet(CIK, *previous_period(YEAR, PERIOD)).build()
    print(f"RE reconciliation:  {inc.simple_reconciliation(bs, bs_prior, dividends_paid=cf.get_dividends_paid() or 0.0)}")
    print(f"Full RE reconciliation: {inc.full_reconciliation(bs, bs_prior, cf, dividends_paid=cf.get_dividends_paid() or 0.0)}")

    # ── Valuation (fiscal-year history) ───────────────────────────────
    history = FinancialHistory.build(CIK, n_years=load_valuation_config().get('history_years', 5))
    inputs  = ValuationInputs(ticker=TICKER, cik=CIK, history=history, price=PRICE)
    print(f"\n── Valuation: {TICKER}  FY{history.years[0]}–FY{history.years[-1]} ──────────────────")

    WACC(inputs).summarize()
    DiscountedCashFlow(inputs).summarize()
    LiquidationValue(inputs).summarize()

    models = [
        DiscountedCashFlow(inputs),
        EarningsPowerValue(inputs),
        AverageEarningsCapitalization(inputs),
        PeterLynchFairValue(inputs),
        DividendDiscountModel(inputs),
        TradingMultiples(inputs, peers=PEERS),
        JustifiedPriceToBook(inputs),
        GrahamNumber(inputs),
        NetCurrentAssetValue(inputs),
        LiquidationValue(inputs),
    ]
    results = [m.value() for m in models]

    print(f"\n{'='*60}")
    print(f"Valuation Summary — {TICKER}" + (f"  (price ${PRICE:,.2f})" if PRICE else ''))
    print(f"{'='*60}")
    for r in results:
        print(f"  {r}")
    # Shared warnings (e.g. placeholder market inputs) are printed once here, not per model
    shared = sorted({w for r in results for w in r.warnings if w.startswith(PLACEHOLDER_WARNING)})
    for w in shared:
        print(f"\n  ⚠  {w}")
    print(f"{'='*60}")
