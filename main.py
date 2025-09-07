import requests
from constants import *
from utils import build_url

def read_api_key(path):
    with open(path, "r") as f:
        return f.read().strip()

if __name__=="__main__":
    # Gather information for the request
    ticker = input("Enter the stock ticker symbol: ").upper()
    api_key = read_api_key("apikey.txt")
    url = build_url(FUNCTION_INCOME_STATEMENT, ticker, api_key)
    # Run request
    response = requests.get(url)
    if response.ok:
        data = response.json()
        print(data)
    else:
        print(f"Error: {response.status_code} - {response.text}")