# **COMPANY VALUATION**

## **Overview**
- **Purpose:** Aiming to provide true company valuation for personal investing using data from the SEC
- **Method:** The following methods will be used:
    | Method | Description |
    |------|-------------|
    | Discounted Cash Flow (DCF) | Estimate intrinsic value by projecting future cash flows and discounting them to present value. |
    | Net Current Asset Value (NCAV) | Current assets minus total liabilities ("net-net" approach). |
    | Asset / Liquidation Value | Value if the company liquidated all assets and paid liabilities. |
    | Earnings Power Value (EPV) | Value based on normalized sustainable earnings assuming no growth. |
    | Average Earnings Capitalization | Apply a conservative multiple to average historical earnings. |
    | Dividend Yield / Dividend Record | Evaluate value based on dividend stability and yield. |
    | Book Value Comparison (P/B) | Compare market price to accounting book value. |
    | Margin of Safety | Buy when price is significantly below conservative intrinsic value. |

## **HOW TO RUN**
- ```py .\main.py```

## **DOCUMENTATION**
- SEC API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC Tickers: https://www.sec.gov/files/company_tickers.json
- SEC Sample Company Facts: https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json

## **BASEPLAN**
```text
CompanyValuation/
│
├── constants.py              # Stores the API endpoint constants
├── utils.py                  # Helper functions (e.g., URL building)
├── alpha_vantage_client.py   # Class to handle Alpha Vantage API interactions
│
├── valuation_models/         # Folder for your valuation models (DCF, etc.)
│   ├── __init__.py
│   ├── dcf.py                # DCF (Discounted Cash Flow) valuation model
│   └── multiples.py          # Other models (e.g., PE, EV/EBITDA)
│
├── organization/
│   └── pdfconversion.py      # Aligning everything in a PDF
│
├── communication/
│   └── whatsapp.py           # Sending message to my whatsapp
│
├── main.py                   # Main entry point to run the script
└── requirements.txt          # Required Python packages (requests, numpy, etc.)
```

## **WHERE TO HOST**
- PythonAnywhere

## TODO
- **Gameplan:**
    - SEC API
    - XBRL Parser
    - Normalized financial database
    - Valuation engine
    - Metrics (ROE, P/B, Graham number, etc.)
    - Manual
        1. Ask user for a Ticker
        2. Take the Ticker and run DCF valuation
            - What is DCF? Discounted cash flow. 
        3. Take the information and format it in PDF
            - What does the report need to have? 
        4. Share pdf in whatsapp and/or gmail
    - Auto
        1. Take a Ticker from the S&P list
        2. Take the Ticker and run DCF valuation
        3. Take the information and format it in PDF
        4. Share pdf in whatsapp and/or gmail