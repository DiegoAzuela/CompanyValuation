# alpha_vantage_client.py
import requests
from constants import FUNCTION_INCOME_STATEMENT, FUNCTION_BALANCE_SHEET, FUNCTION_CASH_FLOW, FUNCTION_OVERVIEW
from utils import build_url, read_api_key

class AlphaVantageClient:
    def __init__(self, api_key_path: str):
        self.api_key = read_api_key(api_key_path)
        
    def get_income_statement(self, symbol: str) -> dict:
        """Gets the income statement for a given stock symbol."""
        url = build_url(FUNCTION_INCOME_STATEMENT, symbol, self.api_key)
        return self._request(url)
    
    def get_balance_sheet(self, symbol: str) -> dict:
        url = build_url(FUNCTION_BALANCE_SHEET, symbol, self.api_key)
        return self._request(url)

    def get_cash_flow(self, symbol: str) -> dict:
        url = build_url(FUNCTION_CASH_FLOW, symbol, self.api_key)
        return self._request(url)

    def get_overview(self, symbol: str) -> dict:
        url = build_url(FUNCTION_OVERVIEW, symbol, self.api_key)
        return self._request(url)

    def _request(self, url: str) -> dict:
        """Sends the GET request to the API and returns parsed JSON."""
        response = requests.get(url)
        if response.ok:
            return response.json()
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")
