#!/usr/bin/env python3
"""
Pulling Ticker: A script to fetch and display stock ticker information
    - https://www.sec.gov/files/company_tickers.json
"""
from dotenv import load_dotenv
from urllib import response
import requests
import json
import os

load_dotenv()

# Define the path to the configuration file
config_file = "config.json"

class TickerInfo:
    """Class to get Ticker information from the SEC"""
    def __init__(self, ticker: str, cik_str: str):
        self.ticker = ticker
        self.cik_str = cik_str
    def __repr__(self) -> None:
        return f"TickerInfo(ticker='{self.ticker}', cik={self.cik_str})"
    @staticmethod
    def load_config() -> None:
        """Load configuration from the config file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Configuration file {config_file} not found.")
            return {}
        except json.JSONDecodeError:
            print(f"Error decoding JSON from the configuration file {config_file}.")
            return {}
    @staticmethod
    def ticker_list():
        """Fetches the list of tickers and their corresponding CIKs from the SEC."""
        config, header_sec = TickerInfo.load_config(), os.getenv("SEC_HEADER")
        url = config['secData']['url_ticker_and_cik']
        headers = {'User-Agent': header_sec}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return [TickerInfo(item['ticker'], item['cik_str']) for item in data.values()]
        except requests.exceptions.RequestException as e:
            print(f"Error fetching ticker information: {e}")
            return []
    @staticmethod
    def seed_db():
        from db.tickers import TickerDB
        tickers = TickerInfo.ticker_list()
        TickerDB.upsert_many(tickers)
        print(f"Seeded {len(tickers)} tickers to DB.")
    @staticmethod
    def fix_cik(cik_str: str) -> str:
        """Utility function to ensure CIK is 10 digits with leading zeros."""
        return cik_str.zfill(10)
    @staticmethod
    def get_financials(cik:str):
        """Fetches financial information for a given CIK from the SEC."""
        config, header_sec = TickerInfo.load_config(), os.getenv("SEC_HEADER")
        cik = TickerInfo.fix_cik(cik)
        url = config['secData']['url_financials'].format(cik=cik)
        headers = {'User-Agent': header_sec}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching financial information: {e}")
            return {}