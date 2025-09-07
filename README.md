# **COMPANY VALUATION**
- **Purpose:** Aiming to provide true company valuation for personal investing

# **DOCUMENTATION**
- https://www.alphavantage.co/documentation/

# **BASEPLAN**
alpha_vantage_valuation_tool/
│
├── constants.py               # Stores the API endpoint constants
├── utils.py                   # Helper functions (e.g., URL building)
├── alpha_vantage_client.py     # Class to handle Alpha Vantage API interactions
├── valuation_models/           # Folder for your valuation models (DCF, etc.)
│   ├── __init__.py
│   ├── dcf.py                  # DCF (Discounted Cash Flow) valuation model
│   └── multiples.py            # Other models (e.g., PE, EV/EBITDA)
│
├── main.py                     # Main entry point to run the script
└── requirements.txt            # Required Python packages (requests, numpy, etc.)

# **WHERE TO HOST**
- PythonAnywhere

# TODO
- Send whatsapp/mail alerts with good investment oportunities