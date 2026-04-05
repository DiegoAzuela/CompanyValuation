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
- SEC Data
    - [SEC Tickers](https://www.sec.gov/files/company_tickers.json)
    - [SEC CIK-Company Mapping](https://www.sec.gov/include/ticker.txt)
    - [Developer Page](https://www.sec.gov/about/developer-resources)
    - [SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) (use this to determine what API to use)
        - [SEC API SDK](https://api.edgarfiling.sec.gov/docs/index.html)    
        - [SEC Sample Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json)
        - [SEC Sample Concept - Accounts Payable](https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/AccountsPayableCurrent.json) 
        - [Frames](data.sec.gov/api/xbrl/frames/)
        - [Taxonomies](https://www.sec.gov/data-research/structured-data/taxonomies-schemas/standard-taxonomies)
            - [Operating Companies](https://www.sec.gov/data-research/structured-data/taxonomies-schemas/standard-taxonomies/operating-companies)
                - [US GAAP](https://fasb.org/projects/fasb-taxonomies)
            - [Investment Companies](https://www.sec.gov/data-research/structured-data/taxonomies-schemas/standard-taxonomies/investment-companies)
            - [Self-Regulatory Organizations](https://www.sec.gov/data-research/standard-taxonomies/self-regulatory-organizations)
            - [Security-Based Swap Entities](https://www.sec.gov/data-research/standard-taxonomies/security-based-swap-data-repositories-and-execution-facilities)
            - [Nationally Recognized Statistical Rating Organizations](https://www.sec.gov/data-research/standard-taxonomies/nationally-recognized-statistical-rating-organizations)


- CONCEPTS EXPLAINED
    - [Balance Sheet](https://www.sec.gov/files/balancesheet-building-blocks.pdf)
    - [Income Statement](https://www.sec.gov/files/income-statement-building-blocks.pdf)
    - [Various](https://www.sec.gov/resources-small-businesses/glossary#FinStatements)
- OPEN INSIDER: http://openinsider.com/
- HOW TO SEE DB:
    - Download DB Browser for SQLite — https://sqlitebrowser.org/dl/
    - Open DB Browser --> File → Open Database --> Browse Data tab

## **LIMITATIONS**
- Current max request rate: 10 requests/second.

## **BASEPLAN**
```text
CompanyValuation/
│
├── constants.py                   # API endpoint constants
│
├── storage/                       # All static/persisted data files
│   ├── tickers.db                 # CIK:ticker SQLite database
│   └── taxonomies_and_concepts.json  # SEC XBRL taxonomy map (2026)
│
├── db/                            # Database access layer
│   ├── __init__.py
│   ├── database.py                # Init, connection, utility functions
│   └── tickers.py                 # Ticker CRUD operations
│
├── data_sources/                  # External API integrations
│   ├── __init__.py
│   └── sec.py                     # EDGAR API calls (frames, concepts, facts)
│
├── financial_statements/          # Builds structured statements from raw SEC data
│   ├── __init__.py
│   ├── balance_sheet.py           # Assembles balance sheet from XBRL concepts
│   └── income_statement.py        # Assembles income statement from XBRL concepts
│
├── valuation_models/              # Valuation logic
│   ├── __init__.py
│   ├── dcf_valuation.py
│   └── multiples.py
│
├── formatting/
│   └── pdf_conversion.py
│
├── communication/
│   └── delivery.py
│
├── main.py
└── requirements.txt
```

## **WHERE TO HOST**
- PythonAnywhere

## TODO
- **Gameplan:**
    - **Data Manipulation**
        1. Initial CIK-Ticker Mapping
        2. SEC DATA for Financial Statements
        3. NEXT STEPS --> Financial Statements
            - Build balance_sheet and income_statement
        4. Formatting P1
            - Financial Statement reporting
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