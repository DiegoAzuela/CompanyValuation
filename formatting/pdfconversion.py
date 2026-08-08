#!/usr/bin/env python3
"""
Description: Content of the PDF file will be:
    - Report Summary: Company, Ticker, Companys Category, Current Stock Price, Graph historical stock price
         __________________________________________________
        | COMPANY - JOHNSON & JOHNSON                      |
        |--------------------------------------------------|
        | Ticker                        |       JNJ        |
        | Companys Category             |    Healthcare    |
        | Companys Current Stock Price  |     $234.18      |
        |--------------------------------------------------|
        | Valuation P/B                 |   $255 (+8.89%)  |
        | Valuation EPV                 |   $255 (+8.89%)  |
        | Valuation DCF                 |   $255 (+8.89%)  |
        | Valuation NCAV                |   $255 (+8.89%)  |
        | Valuation Yield / Record      |   $255 (+8.89%)  |
        | Valuation Margin of Safety    |   $255 (+8.89%)  |
        | Valuation Avg Earning Capit   |   $255 (+8.89%)  |
        | Valuation Asset/Liquidation   |   $255 (+8.89%)  |
        |--------------------------------------------------|
        | Graph Historical Stock Price                     |
        |               |                 *                |
        |               |      *        *                  |
        |               |    *   *    *                    |
        |               |  *      * *                      |
        |               |*_ _ _ _ _ _ _ _ _                |
        |__________________________________________________|
    - Financial Statements (Balance Sheet, Cash Flow Statement, Income Statement)
    - Valuation Models (reference - https://valueinvesting.io/AAPL/valuation/intrinsic-value)

    - Library for PDF creation --> ReportLab — best for financial reports (recommended)
"""
