# https://ranaroussi.github.io/yfinance/
# https://ranaroussi.github.io/yfinance/reference/index.html
import yfinance as yf

if __name__=="__main__":
    data_ticker = input("Please provide a TICKET: ")
    information = yf.Ticker(data_ticker)
    print(information.info)