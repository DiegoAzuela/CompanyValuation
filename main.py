from db.database import TickerDatabase
from data_sources.sec import TickerInfo
from dotenv import load_dotenv
import os

TickerDatabase.init_db()
TickerInfo.seed_db()

load_dotenv()

if __name__ == "__main__":
    # Example usage of the TickerInfo class to fetch ticker information
    tickers = TickerInfo.ticker_list()
    print(f"Printing one of the tickers: {tickers[0]}")
    # Now lets take this CIK and fetch it from the database to verify it was stored correctly
    from db.tickers import TickerDB
    ticker = tickers[0].ticker
    cik_from_db = TickerDB.get_cik(ticker)
    print(f"CIK for ticker {ticker} from DB: {cik_from_db}")
    # Now lets pull the financials for this ticker
    financial_test=TickerInfo.get_financials(cik_from_db)
    print(f"Financials for ticker {ticker} with CIK {cik_from_db}: {financial_test}")