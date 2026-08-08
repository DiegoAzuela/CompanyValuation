from financial_statements.balance_sheet import BalanceSheet
from financial_statements.income_statement import IncomeStatement
from financial_statements.cash_flow_statement import CashFlowStatement
from financial_statements import FinancialStatement, Period
from db.database import TickerDatabase 
from data_sources.sec import SecData
from db.tickers import TickerDB
from dotenv import load_dotenv
import os

TickerDatabase.init_db()
SecData.seed_db()

# Actual financial statements - https://www.apple.com/newsroom/pdfs/fy2025-q2/FY25_Q2_Consolidated_Financial_Statements.pdf
load_dotenv()
taxonomy = "us-gaap"
TICKER = "AAPL"
CIK  = "320193"  # Apple
YEAR = 2025
PERIOD = Period.Q2

if __name__ == "__main__":
    # Example usage of the SecData class to fetch ticker information
    tickers = SecData.ticker_list()
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

    # reconciliation requires a prior-year balance sheet
    bs_prior = BalanceSheet(CIK, YEAR - 1, PERIOD).build()
    print(f"RE reconciliation:  {inc.simple_reconciliation(bs, bs_prior, dividends_paid=cf.get_dividends_paid() or 0.0)}")
    print(f"Full RE reconciliation: {inc.full_reconciliation(bs, bs_prior, cf, dividends_paid=cf.get_dividends_paid() or 0.0)}")
