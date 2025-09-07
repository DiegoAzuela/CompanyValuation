from alpha_vantage_client import AlphaVantageClient

if __name__=="__main__":
    ticker = input("Enter the stock ticker symbol: ").upper()
    client = AlphaVantageClient("apikey.txt")
    
    data = client.get_income_statement(ticker)
    print(data)