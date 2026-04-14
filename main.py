from financial_statements.balance_sheet import BalanceSheet
from financial_statements import FinancialStatement, Period
from db.database import TickerDatabase
from data_sources.sec import SecData
from dotenv import load_dotenv
import os

TickerDatabase.init_db()
SecData.seed_db()

load_dotenv()
taxonomy = "us-gaap"
concept = "AccountsPayableCurrent"
unit = "USD"
frame = "CY2019Q1I"

if __name__ == "__main__":
    # Example usage of the SecData class to fetch ticker information
    tickers = SecData.ticker_list()
    print(f"Printing one of the tickers: {tickers[0]}")
    # Now lets take this CIK and fetch it from the database to verify it was stored correctly
    from db.tickers import TickerDB
    ticker = tickers[0].ticker
    cik_from_db = TickerDB.get_cik(ticker)
    print(f"CIK for ticker {ticker} from DB: {cik_from_db}")

    # Now lets pull the company facts for this ticker
    # fact_test=SecData.get_companyfacts(cik_from_db)
    # print(f"CompanyFacts for ticker {ticker} with CIK {cik_from_db}: {fact_test}")

    # Now lets pull a specific concept for this ticker
    # concept_test=SecData.get_concept(cik_from_db, taxonomy, concept)
    # print(f"Concept for ticker {ticker} with CIK {cik_from_db}, Taxonomy {taxonomy}, Concept {concept}: {concept_test}")

    # Now lets pull a parsed concept for this ticker
    # concept_withframe_test=SecData.get_concept_frameAndCik(cik_from_db,taxonomy, concept,frame, unit)
    # print(f"Concept with frame for: {concept_withframe_test}")
    # print(concept_withframe_test)

    # Now lets pull a parsed concept for this ticker
    bs = BalanceSheet("320193", 2023, Period.FY).build()
    print(f"Target date resolved to: {bs._target_date}")
    print(f"Total Assets:       {bs.get_total_assets():,.0f}")
    print(f"Total Liabilities:  {bs.get_total_liabilities():,.0f}")
    print(f"Total Equity:       {bs.get_total_equity():,.0f}")
    print(f"Balanced:           {bs.is_balanced()}")
    bs.summarize()