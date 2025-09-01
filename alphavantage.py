# https://www.alphavantage.co/documentation/
import requests

def read_api_key(path):
    with open(path, "r") as f:
        return f.read().strip()

if __name__=="__main__":
    api_key = read_api_key("apikey.txt")
    base_url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey={key}'
    url = f"{base_url}{api_key}"
    r = requests.get(url)
    data = r.json()

    print(data)