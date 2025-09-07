import json
from alpha_vantage_client import AlphaVantageClient as avc

if __name__=="__main__":
    ticker = input("Enter the stock ticker symbol: ").upper()
    client = avc("_token/apikey.txt")
    
    data = client.get_balance_sheet(ticker)
    print(json.dumps(data, indent=2))  # pretty JSON string