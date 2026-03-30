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
- SEC Developer Page: https://www.sec.gov/about/developer-resources
    - SEC API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces (use this to determine what API to use)
        - SEC API Overview: https://www.sec.gov/files/edgar/filer-information/api-overview.pdf
        - Check "Other Sources": https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
            - Financial Statements: https://www.sec.gov/files/financial-statement-data-sets.pdf
    - SEC Tickers: https://www.sec.gov/files/company_tickers.json
    - SEC CIK-Company Mapping: https://www.sec.gov/include/ticker.txt
    - SEC Dataset: https://www.sec.gov/files/financial-statement-data-sets.pdf
    - SEC Sample Company Facts: https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
    - SEC Timestamps Explained: https://www.sec.gov/files/edgar/pds_dissemination_spec.pdf
    - SEC FullText Review: https://www.sec.gov/edgar/searchedgar/edgarfulltextfaq.htm
- OPEN INSIDER: http://openinsider.com/
- HOW TO SEE DB:
    - Download DB Browser for SQLite — https://sqlitebrowser.org/dl/
    - Open DB Browser --> File → Open Database --> Browse Data tab

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
    - **Data Manipulation**
        1. DONE - CIK-Ticker Mapping: https://www.sec.gov/include/ticker.txt
            - data/tickers.db stores the data 
        2. NEXT STEPS: SEC API: Pull Financials
        3. Parse Info: XBRL Parser
        4. Normalized financial database
        5. Valuation engine
        6. Metrics (ROE, P/B, Graham number, etc.)
    - **Integration**
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