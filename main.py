from db.database import init_db
from data_sources.sec import TickerInfo
from dotenv import load_dotenv
import os

TickerInfo.seed_db()
init_db()

load_dotenv()

if __name__ == "__main__":
    # Example usage of the TickerInfo class to fetch ticker information
    tickers = TickerInfo.ticker_list()
    print(f"Fetched {tickers} tickers from the SEC")