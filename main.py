from db.database import TickerDatabase
from data_sources.sec import TickerInfo
from dotenv import load_dotenv
import os

TickerDatabase.init_db()
TickerInfo.seed_db()

load_dotenv()
taxonomy = "us-gaap"
concept = "AccountsPayableCurrent"
year = 2019
quarter = 1

if __name__ == "__main__":
    # Example usage of the TickerInfo class to fetch ticker information
    tickers = TickerInfo.ticker_list()
    print(f"Printing one of the tickers: {tickers[0]}")
    # Now lets take this CIK and fetch it from the database to verify it was stored correctly
    from db.tickers import TickerDB
    ticker = tickers[0].ticker
    cik_from_db = TickerDB.get_cik(ticker)
    print(f"CIK for ticker {ticker} from DB: {cik_from_db}")

    # Now lets pull the company facts for this ticker
    # fact_test=TickerInfo.get_companyfacts(cik_from_db)
    # print(f"CompanyFacts for ticker {ticker} with CIK {cik_from_db}: {fact_test}")

    # Now lets pull a specific concept for this ticker
    # concept_test=TickerInfo.get_concept(cik_from_db, taxonomy, concept)
    # print(f"Concept for ticker {ticker} with CIK {cik_from_db}, Taxonomy {taxonomy}, Concept {concept}: {concept_test}")

    # Now lets pull a parsed concept for this ticker
    concept_withframe_test=TickerInfo.get_concept_frameAndCik(cik_from_db,taxonomy, concept, year, quarter)
    print(f"Concept with frame for ticker {ticker}, Taxonomy {taxonomy}, Concept {concept}: {concept_withframe_test}")
    print(concept_withframe_test)