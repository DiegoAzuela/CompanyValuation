#!/usr/bin/env python3
"""
Description: Assembles an income statement for a given CIK, year, and period by iterating
over the concept fallback chains defined in taxonomies_and_concepts.json.

Layer responsibilities:
  data_sources/sec.py        → fetches raw concept values from EDGAR
  financial_statements/      → assembles raw values into structured statements
  valuation_models/          → consumes finished statements for DCF, multiples, etc.

Usage:
    bs = IncomeStatement(cik="320193", year=2023, period=Period.FY).build()
    bs.summarize()

    total_assets = bs.get_total_assets()
    print(bs.is_balanced())
"""
