#!/usr/bin/env python3
"""
Description: Pulls structured financial data from the SEC's EDGAR API.

--- Layer Responsibility ---
This module is the ONLY place in the project that talks to the SEC API.
No other module should make direct HTTP requests to EDGAR.

    sec.py                     --> raw HTTP fetches from EDGAR
    financial_statements/      --> assembles raw values into balance sheets / income statements
    valuation_models/          --> consumes finished statements for DCF, multiples, etc.

--- SEC EDGAR API Endpoints Used ---
All base URLs are defined in config.json under secData. Key endpoints:

  1. Ticker + CIK list
     GET https://www.sec.gov/files/company_tickers.json
     Returns all public company tickers and their CIKs. Used to seed the local DB.

  2. Company Facts (all concepts, all periods, for one company)
     GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
     Returns every XBRL-tagged fact ever filed by a company. Useful for
     discovering which tags a company actually uses (since not every company
     uses the standard tag — e.g. Apple uses MarketableSecuritiesCurrent
     instead of ShortTermInvestments).

  3. Company Concept (one concept, all periods, for one company)
     GET https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json
     Returns all historical values for a single XBRL concept for one company.
     Returns 404 if the company has never filed that specific tag — use the
     fallback candidate chains in taxonomies_and_concepts.json to handle this.

  4. Concept Frame (one concept, one period, ALL companies)
     GET https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{frame}.json
     Returns the value of one concept for every company that filed it in a
     given period. Used to look up a specific company's value by CIK.

     Frame string format:
       Balance sheet  (instant):  CY{year}Q{n}I   e.g. CY2023Q4I
       Income stmt    (duration): CY{year}Q{n}     e.g. CY2023Q1
       Full-year      (duration): CY{year}          e.g. CY2023
       Note: CY{year}I does NOT exist — year-end balance sheet = CY{year}Q4I

     Unit string:
       Monetary amounts:  USD
       Per-share amounts: USD/shares     (e.g. EarningsPerShareDiluted)
       Share counts:      shares         (e.g. WeightedAverageNumberOfSharesOutstandingBasic)

--- CIK Formatting ---
The companyfacts and companyconcept endpoints require a zero-padded 10-digit
CIK (e.g. CIK0000320193). The frames endpoint uses bare integer CIKs in its
response data. fix_cik() handles the padding; int(cik) handles the lookup.

--- Authentication ---
The SEC requires a User-Agent header identifying your application and contact
email. Store this in your .env file as SEC_HEADER and never hardcode it.
Format: "YourAppName/1.0 your@email.com"
See: https://www.sec.gov/os/accessing-edgar-data

--- Rate Limiting ---
The SEC enforces a limit of 10 requests per second. The lru_cache on
get_concept_frame avoids redundant requests for the same frame — the full
frame payload (often 3,000+ companies) is fetched once and reused for all
CIK lookups against the same concept + period.
"""

from functools import lru_cache
from dotenv import load_dotenv
import requests
import json
import os

load_dotenv()

# Path to the shared configuration file
_CONFIG_FILE = "config.json"


class SecData:
    """
    Static utility class for fetching data from the SEC EDGAR API.

    All methods are static — this class is a namespace, not an instance.
    Call methods directly: SecData.get_companyfacts("320193")
    """

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config() -> dict:
        """
        Loads the project config from config.json.
        Returns an empty dict on failure so callers can fail gracefully.
        """
        try:
            with open(_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[SecData] Config file '{_CONFIG_FILE}' not found.")
            return {}
        except json.JSONDecodeError:
            print(f"[SecData] Failed to parse '{_CONFIG_FILE}' as JSON.")
            return {}

    @staticmethod
    def _get_headers() -> dict:
        """Builds the request headers using the SEC_HEADER env variable."""
        return {'User-Agent': os.getenv('SEC_HEADER', '')}

    @staticmethod
    def fix_cik(cik: str) -> str:
        """
        Zero-pads a CIK to 10 digits, as required by the companyfacts
        and companyconcept endpoints.

        Example: "320193" → "0000320193"
        """
        return str(cik).zfill(10)

    # ------------------------------------------------------------------
    # Ticker + CIK list
    # ------------------------------------------------------------------

    @staticmethod
    def get_fiscal_year_end(cik: str, year: int, period) -> str:
        """
        Looks up the actual balance sheet date for a given company/year/period
        from the SEC submissions endpoint, handling non-calendar fiscal years.

        Falls back to calendar quarter-end dates if submissions lookup fails.
        """
        from financial_statements import Period  # avoid circular import

        fallback = {
            'Q1': f"{year}-03-31",
            'Q2': f"{year}-06-30",
            'Q3': f"{year}-09-30",
            'Q4': f"{year}-12-31",
            'FY': f"{year}-12-31",
        }
        period_key = 'Q4' if period == Period.FY else period.value

        try:
            config = SecData._load_config()
            cik_padded = SecData.fix_cik(cik)
            url = config['secData']['url_submissions'].format(cik=cik_padded)
            response = requests.get(url, headers=SecData._get_headers())
            response.raise_for_status()
            data = response.json()

            filings = data.get('filings', {}).get('recent', {})
            forms       = filings.get('form', [])
            report_dates = filings.get('reportDate', [])

            # Find 10-K filings where the report year matches
            target_form = '10-K' if period_key == 'Q4' else '10-Q'
            for form, date in zip(forms, report_dates):
                if form == target_form and date.startswith(str(year)):
                    return date  # e.g. "2023-09-30" for Apple FY2023

        except Exception as e:
            print(f"[SecData] Falling back to calendar date for CIK {cik}: {e}")

        return fallback[period_key]


    @staticmethod
    def ticker_list() -> list:
        """
        Fetches the full list of public company tickers and CIKs from the SEC.
        Used to seed the local tickers.db database.

        Returns:
            List of TickerInfo instances, or [] on failure.
        """
        from data_sources.sec import TickerInfo  # avoid circular at module level

        config = SecData._load_config()
        url    = config.get('secData', {}).get('url_ticker_and_cik', '')

        try:
            response = requests.get(url, headers=SecData._get_headers())
            response.raise_for_status()
            data = response.json()
            return [TickerInfo(item['ticker'], item['cik_str']) for item in data.values()]
        except requests.exceptions.RequestException as e:
            print(f"[SecData] Error fetching ticker list: {e}")
            return []

    @staticmethod
    def seed_db() -> None:
        """Seeds the local SQLite database with the full SEC ticker + CIK list."""
        from db.tickers import TickerDB
        tickers = SecData.ticker_list()
        TickerDB.upsert_many(tickers)
        print(f"[SecData] Seeded {len(tickers)} tickers to DB.")

    # ------------------------------------------------------------------
    # Company Facts — all concepts, all periods, one company
    # ------------------------------------------------------------------

    @staticmethod
    def get_companyfacts(cik: str) -> dict:
        """
        Fetches every XBRL-tagged fact ever filed by a company.

        Useful for:
          - Discovering which tags a company actually uses
          - Pulling all historical values for all concepts at once
          - Debugging missing concepts (e.g. why ShortTermInvestments returns 404)

        Args:
            cik: Company CIK as a string (padding is applied automatically)

        Returns:
            Full companyfacts JSON, or {} on failure.
        """
        config = SecData._load_config()
        cik    = SecData.fix_cik(cik)
        url    = config['secData']['url_companyfacts'].format(cik=cik)

        try:
            response = requests.get(url, headers=SecData._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[SecData] Error fetching companyfacts for CIK {cik}: {e}")
            return {}

    # ------------------------------------------------------------------
    # Company Concept — one concept, all periods, one company
    # ------------------------------------------------------------------

    @staticmethod
    def get_concept(cik: str, taxonomy: str, concept: str) -> dict:
        """
        Fetches all historical values for a single XBRL concept for one company.

        Returns 404 (empty dict) if the company has never filed that specific
        tag. This is expected — use the fallback candidate chains in
        taxonomies_and_concepts.json to try alternative tags.

        Args:
            cik:      Company CIK (padding applied automatically)
            taxonomy: "us-gaap" or "ifrs-full"
            concept:  XBRL tag e.g. "AccountsPayableCurrent"

        Returns:
            Concept JSON with all historical filings, or {} on failure / 404.
        """
        config = SecData._load_config()
        cik    = SecData.fix_cik(cik)
        url    = config['secData']['url_concept'].format(
                    cik=cik, taxonomy=taxonomy, concept=concept)

        try:
            response = requests.get(url, headers=SecData._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[SecData] Error fetching concept {concept} for CIK {cik}: {e}")
            return {}

    # ------------------------------------------------------------------
    # Concept Frame — one concept, one period, ALL companies
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=128)
    def get_concept_frame(taxonomy: str, concept: str, unit: str, frame: str) -> dict:
        """
        Fetches a concept frame — the value of one XBRL concept for every
        company that filed it in a given period.

        Results are cached by (taxonomy, concept, unit, frame) so the full
        payload is only fetched once per unique combination, regardless of
        how many CIKs are looked up against it.

        Args:
            taxonomy: "us-gaap" or "ifrs-full"
            concept:  XBRL tag e.g. "AccountsPayableCurrent"
            unit:     "USD", "USD/shares", or "shares"
            frame:    Pre-built SEC frame string:
                        Balance sheet (instant):  "CY2023Q4I"
                        Income stmt (duration):   "CY2023Q1"
                        Full-year (duration):     "CY2023"

        Returns:
            Frame JSON with an added '_index' dict keyed by integer CIK
            for O(1) per-company lookups. Returns {} on failure.
        """
        config = SecData._load_config()
        url    = config['secData']['url_concept_withframe'].format(
                    taxonomy=taxonomy, concept=concept, unit=unit, frame=frame)

        try:
            response = requests.get(url, headers=SecData._get_headers())
            response.raise_for_status()
            raw = response.json()

            # Build a CIK → record index for O(1) lookups in get_concept_frameAndCik.
            # CIKs are bare integers in the frame response (not zero-padded strings).
            raw['_index'] = {record['cik']: record for record in raw.get('data', [])}
            return raw

        except requests.exceptions.RequestException as e:
            print(f"[SecData] Error fetching frame [{taxonomy}/{concept}/{unit}/{frame}]: {e}")
            return {}

    @staticmethod
    def get_concept_frameAndCik(
        cik: str,
        taxonomy: str,
        concept: str,
        frame: str,
        unit: str = 'USD'
    ) -> dict:
        """
        Fetches the value of a single XBRL concept for one company within
        a specific period, using the frames endpoint.

        This is the primary method called by financial_statements/ — it is
        called once per candidate tag per line item during statement assembly.

        Args:
            cik:      Company CIK as a string
            taxonomy: "us-gaap" or "ifrs-full"
            concept:  XBRL tag e.g. "AccountsPayableCurrent"
            frame:    Pre-built SEC frame string e.g. "CY2023Q4I", "CY2023"
            unit:     "USD" (default), "USD/shares" for EPS, "shares" for share counts

        Returns:
            {
                'val':  float or None,   — the reported value
                'unit': str              — unit of measure from the SEC response
            }
            or {} if the frame fetch failed or the CIK was not in the frame.
        """
        frame_data = SecData.get_concept_frame(taxonomy, concept, unit, frame)
        if not frame_data:
            return {}

        # CIKs are integers in the frame response — cast before lookup
        record = frame_data.get('_index', {}).get(int(cik))

        if record is None:
            print(f"[SecData] CIK {cik} not found in frame [{taxonomy}/{concept}/{unit}/{frame}]")
            return {}

        return {
            'val':  record.get('val'),
            'unit': frame_data.get('uom'),
        }


# ------------------------------------------------------------------
# TickerInfo — lightweight data container returned by ticker_list()
# ------------------------------------------------------------------

class TickerInfo:
    """
    Lightweight container for a ticker + CIK pair returned by the SEC
    ticker list endpoint. Used as the unit of transfer into the local DB.
    """

    def __init__(self, ticker: str, cik_str: str):
        self.ticker  = ticker
        self.cik_str = cik_str

    def __repr__(self) -> str:
        return f"TickerInfo(ticker='{self.ticker}', cik='{self.cik_str}')"