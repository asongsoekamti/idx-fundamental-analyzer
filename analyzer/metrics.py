"""Modul perhitungan metrik fundamental.

Semua fungsi di sini menerima `StockData` (dari `fetcher`) dan mengembalikan
dict berisi metrik terhitung. Jika field sumber tidak tersedia, nilainya `None`
(bukan 0) supaya layer presentation bisa menampilkan "N/A" alih-alih nol palsu.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analyzer.fetcher import StockData


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Pembagian aman: None kalau pembilang/penyebut None/0/NaN."""
    if numerator is None or denominator is None:
        return None
    try:
        n = float(numerator)
        d = float(denominator)
    except (TypeError, ValueError):
        return None
    if d == 0 or np.isnan(n) or np.isnan(d):
        return None
    return n / d


def _get_row(df: pd.DataFrame, candidates: list[str]) -> pd.Series | None:
    """Cari baris pertama yang cocok dari beberapa nama alternatif.

    yfinance bisa pakai 'Net Income' atau 'NetIncome' tergantung versi.
    """
    if df is None or df.empty:
        return None
    for name in candidates:
        if name in df.index:
            return df.loc[name]
    # fallback: case-insensitive contains
    lower_map = {str(i).lower().replace(" ", ""): i for i in df.index}
    for name in candidates:
        key = name.lower().replace(" ", "")
        if key in lower_map:
            return df.loc[lower_map[key]]
    return None


def _latest(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    val = series.dropna()
    if val.empty:
        return None
    return float(val.iloc[0])


def _cagr(series: pd.Series | None, years: int = 3) -> float | None:
    """Compound Annual Growth Rate dari series tahunan (yfinance: kolom terkini = paling kiri).

    Return desimal (0.15 = 15%). None jika data tidak cukup atau ada nilai negatif/nol.
    """
    if series is None:
        return None
    clean = series.dropna()
    if len(clean) < 2:
        return None
    n = min(years, len(clean) - 1)
    latest = float(clean.iloc[0])
    earliest = float(clean.iloc[n])
    if earliest <= 0 or latest <= 0:
        return None
    return (latest / earliest) ** (1 / n) - 1


def _yoy_growth(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    clean = series.dropna()
    if len(clean) < 2:
        return None
    latest = float(clean.iloc[0])
    prev = float(clean.iloc[1])
    if prev == 0:
        return None
    return (latest - prev) / abs(prev)


def _stdev(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    clean = series.dropna()
    if len(clean) < 2:
        return None
    return float(clean.std())


def compute_metrics(data: StockData) -> dict[str, Any]:  # noqa: C901 - banyak metrik wajar
    """Hitung metrik fundamental dari `StockData`. Mengembalikan flat dict.

    Kunci dibagi grup secara konvensional di README; di sini cuma dict flat
    supaya gampang di-render ke tabel.
    """
    info = data.info or {}
    fin = data.financials
    bal = data.balance_sheet
    cf = data.cashflow

    # Baris-baris utama dari laporan tahunan
    revenue = _get_row(fin, ["Total Revenue", "TotalRevenue", "Revenue"])
    cogs = _get_row(fin, ["Cost Of Revenue", "CostOfRevenue", "Cost of Revenue"])
    gross_profit = _get_row(fin, ["Gross Profit", "GrossProfit"])
    op_income = _get_row(fin, ["Operating Income", "OperatingIncome"])
    net_income = _get_row(fin, ["Net Income", "NetIncome", "Net Income Common Stockholders"])
    ebitda_row = _get_row(fin, ["EBITDA", "Normalized EBITDA"])
    interest_expense = _get_row(fin, ["Interest Expense", "InterestExpense"])
    sga = _get_row(fin, ["Selling General And Administration", "SellingGeneralAndAdministrative"])
    rnd = _get_row(fin, ["Research And Development", "ResearchAndDevelopment"])

    total_assets = _get_row(bal, ["Total Assets", "TotalAssets"])
    total_equity = _get_row(
        bal, ["Total Equity Gross Minority Interest", "Stockholders Equity", "TotalStockholderEquity"]
    )
    total_debt_row = _get_row(bal, ["Total Debt", "TotalDebt"])
    cash_row = _get_row(bal, ["Cash And Cash Equivalents", "CashAndCashEquivalents", "Cash"])
    current_assets = _get_row(bal, ["Current Assets", "CurrentAssets", "Total Current Assets"])
    current_liab = _get_row(
        bal, ["Current Liabilities", "CurrentLiabilities", "Total Current Liabilities"]
    )
    inventory = _get_row(bal, ["Inventory"])
    receivables = _get_row(bal, ["Accounts Receivable", "Receivables", "Net Receivables"])
    payables = _get_row(bal, ["Accounts Payable", "Payables"])
    retained = _get_row(bal, ["Retained Earnings", "RetainedEarnings"])
    intangibles = _get_row(bal, ["Goodwill And Other Intangible Assets", "Goodwill"])

    capex = _get_row(cf, ["Capital Expenditure", "CapitalExpenditure", "Capital Expenditures"])
    op_cf = _get_row(cf, ["Operating Cash Flow", "OperatingCashFlow", "Cash Flow From Operations"])
    fcf = _get_row(cf, ["Free Cash Flow", "FreeCashFlow"])

    # Nilai terkini (LTM proxy = tahun terakhir di laporan tahunan yfinance)
    revenue_latest = _latest(revenue)
    net_income_latest = _latest(net_income)
    op_income_latest = _latest(op_income)
    gross_profit_latest = _latest(gross_profit)
    ebitda_latest = _latest(ebitda_row) or info.get("ebitda")
    total_assets_latest = _latest(total_assets) or info.get("totalAssets")
    total_equity_latest = _latest(total_equity)
    total_debt_latest = _latest(total_debt_row) or info.get("totalDebt")
    cash_latest = _latest(cash_row) or info.get("totalCash")
    fcf_latest = _latest(fcf) or info.get("freeCashflow")
    op_cf_latest = _latest(op_cf) or info.get("operatingCashflow")
    capex_latest = _latest(capex)
    intangibles_latest = _latest(intangibles) or 0
    retained_latest = _latest(retained)

    # Harga & valuasi pasar
    price = data.current_price
    shares = info.get("sharesOutstanding")
    market_cap = info.get("marketCap")
    enterprise_value = info.get("enterpriseValue")
    eps = info.get("trailingEps")
    forward_eps = info.get("forwardEps")
    book_value = info.get("bookValue")  # per share

    # Beberapa rasio dari info kalau ada, fallback ke perhitungan manual
    per = info.get("trailingPE") or _safe_div(price, eps)
    forward_per = info.get("forwardPE") or _safe_div(price, forward_eps)
    pbv = info.get("priceToBook") or _safe_div(price, book_value)
    psr = info.get("priceToSalesTrailing12Months") or _safe_div(
        market_cap, revenue_latest
    )
    peg = info.get("pegRatio") or info.get("trailingPegRatio")
    ev_ebitda = _safe_div(enterprise_value, ebitda_latest)
    ev_sales = _safe_div(enterprise_value, revenue_latest)

    # Margin
    gross_margin = info.get("grossMargins") or _safe_div(gross_profit_latest, revenue_latest)
    operating_margin = info.get("operatingMargins") or _safe_div(op_income_latest, revenue_latest)
    net_margin = info.get("profitMargins") or _safe_div(net_income_latest, revenue_latest)
    ebitda_margin = info.get("ebitdaMargins") or _safe_div(ebitda_latest, revenue_latest)
    cf_margin = _safe_div(op_cf_latest, revenue_latest)

    # Return
    roa = info.get("returnOnAssets") or _safe_div(net_income_latest, total_assets_latest)
    roe = info.get("returnOnEquity") or _safe_div(net_income_latest, total_equity_latest)
    invested_capital = None
    if total_equity_latest is not None and total_debt_latest is not None:
        invested_capital = total_equity_latest + total_debt_latest
    # ROIC sederhana: NOPAT proxy = operating income * (1 - tax). Asumsi pajak 22% (UU PPh ID).
    nopat = op_income_latest * (1 - 0.22) if op_income_latest is not None else None
    roic = _safe_div(nopat, invested_capital)
    roi = _safe_div(net_income_latest, invested_capital)  # proxy sederhana

    # Likuiditas
    current_ratio = info.get("currentRatio") or _safe_div(_latest(current_assets), _latest(current_liab))
    quick_ratio = info.get("quickRatio") or _safe_div(
        (_latest(current_assets) or 0) - (_latest(inventory) or 0),
        _latest(current_liab),
    )
    cash_ratio = _safe_div(cash_latest, _latest(current_liab))

    # Leverage
    der = info.get("debtToEquity")
    if der is not None and der > 5:
        # yfinance kadang return DER dalam persen (misal 150 berarti 1.5x).
        der = der / 100
    if der is None:
        der = _safe_div(total_debt_latest, total_equity_latest)
    debt_to_asset = _safe_div(total_debt_latest, total_assets_latest)
    net_debt = None
    if total_debt_latest is not None and cash_latest is not None:
        net_debt = total_debt_latest - cash_latest
    net_debt_ebitda = _safe_div(net_debt, ebitda_latest)
    interest_coverage = _safe_div(op_income_latest, abs(_latest(interest_expense)) if _latest(interest_expense) else None)

    # Growth
    revenue_growth = info.get("revenueGrowth") or _yoy_growth(revenue)
    earnings_growth = info.get("earningsGrowth") or _yoy_growth(net_income)
    revenue_cagr_3y = _cagr(revenue, years=3)
    revenue_cagr_5y = _cagr(revenue, years=5)
    net_income_cagr_3y = _cagr(net_income, years=3)
    op_income_growth = _yoy_growth(op_income)
    asset_growth = _yoy_growth(total_assets)
    equity_growth = _yoy_growth(total_equity)

    # EPS growth proxy dari net income growth (yfinance jarang expose EPS history)
    eps_growth = info.get("earningsQuarterlyGrowth") or earnings_growth

    # Konsistensi & margin trend
    net_margin_series = None
    if net_income is not None and revenue is not None:
        try:
            net_margin_series = (net_income / revenue).dropna()
        except Exception:
            net_margin_series = None
    margin_stability = _stdev(net_margin_series)  # makin kecil makin stabil
    margin_expansion = None
    if net_margin_series is not None and len(net_margin_series) >= 2:
        margin_expansion = float(net_margin_series.iloc[0]) - float(net_margin_series.iloc[-1])

    # Cash conversion cycle
    dso = _safe_div(_latest(receivables) * 365 if _latest(receivables) else None, revenue_latest)
    dio = _safe_div(_latest(inventory) * 365 if _latest(inventory) else None, _latest(cogs))
    dpo = _safe_div(_latest(payables) * 365 if _latest(payables) else None, _latest(cogs))
    ccc = None
    if all(x is not None for x in (dso, dio, dpo)):
        ccc = dso + dio - dpo

    # Turnover
    asset_turnover = _safe_div(revenue_latest, total_assets_latest)
    inv_turnover = _safe_div(_latest(cogs), _latest(inventory))
    recv_turnover = _safe_div(revenue_latest, _latest(receivables))
    pay_turnover = _safe_div(_latest(cogs), _latest(payables))

    # Working capital
    wc = None
    if _latest(current_assets) is not None and _latest(current_liab) is not None:
        wc = _latest(current_assets) - _latest(current_liab)
    wc_ratio = _safe_div(wc, revenue_latest)

    # CapEx ratio
    capex_to_rev = _safe_div(abs(capex_latest) if capex_latest is not None else None, revenue_latest)

    # Cost structure
    sga_ratio = _safe_div(_latest(sga), revenue_latest)
    opex_ratio = _safe_div((_latest(sga) or 0) + (_latest(rnd) or 0), revenue_latest)
    rnd_ratio = _safe_div(_latest(rnd), revenue_latest)

    # Tangible book value per share
    tbv = None
    if total_equity_latest is not None and shares:
        tbv = (total_equity_latest - intangibles_latest) / shares

    # Share dilution
    shares_prev = info.get("sharesOutstandingPriorYear") or info.get("floatShares")
    share_dilution = None
    if shares and shares_prev:
        share_dilution = (shares - shares_prev) / shares_prev

    return {
        # Identitas
        "ticker": data.ticker,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": info.get("currency", "IDR"),
        "current_price": price,
        # Ukuran
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "shares_outstanding": shares,
        # P&L
        "revenue": revenue_latest,
        "gross_profit": gross_profit_latest,
        "operating_profit": op_income_latest,
        "net_profit": net_income_latest,
        "ebitda": ebitda_latest,
        "eps": eps,
        "forward_eps": forward_eps,
        "cogs": _latest(cogs),
        # Margin
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "net_margin": net_margin,
        "ebitda_margin": ebitda_margin,
        "cash_flow_margin": cf_margin,
        # Return
        "roa": roa,
        "roe": roe,
        "roic": roic,
        "roi": roi,
        # Valuasi
        "per": per,
        "forward_per": forward_per,
        "pbv": pbv,
        "psr": psr,
        "peg": peg,
        "ev_ebitda": ev_ebitda,
        "ev_sales": ev_sales,
        "book_value_per_share": book_value,
        "tangible_book_value_per_share": tbv,
        # Dividen
        "dividend_yield": info.get("dividendYield"),
        "payout_ratio": info.get("payoutRatio"),
        "dividend_rate": info.get("dividendRate"),
        # Cash flow
        "free_cash_flow": fcf_latest,
        "operating_cash_flow": op_cf_latest,
        "capex": capex_latest,
        "capex_to_revenue": capex_to_rev,
        # Likuiditas
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "cash_ratio": cash_ratio,
        "working_capital": wc,
        "working_capital_ratio": wc_ratio,
        # Leverage
        "der": der,
        "debt_to_asset": debt_to_asset,
        "total_debt": total_debt_latest,
        "net_debt": net_debt,
        "net_debt_to_ebitda": net_debt_ebitda,
        "interest_coverage": interest_coverage,
        # Growth
        "revenue_growth_yoy": revenue_growth,
        "earnings_growth_yoy": earnings_growth,
        "eps_growth": eps_growth,
        "operating_income_growth": op_income_growth,
        "asset_growth": asset_growth,
        "equity_growth": equity_growth,
        "revenue_cagr_3y": revenue_cagr_3y,
        "revenue_cagr_5y": revenue_cagr_5y,
        "net_income_cagr_3y": net_income_cagr_3y,
        # Konsistensi
        "net_margin_stability_stdev": margin_stability,
        "margin_expansion_trend": margin_expansion,
        # Turnover & efisiensi
        "asset_turnover": asset_turnover,
        "inventory_turnover": inv_turnover,
        "receivable_turnover": recv_turnover,
        "payable_turnover": pay_turnover,
        "dso": dso,
        "dio": dio,
        "dpo": dpo,
        "cash_conversion_cycle": ccc,
        # Cost structure
        "sga_ratio": sga_ratio,
        "opex_ratio": opex_ratio,
        "rnd_to_revenue": rnd_ratio,
        # Equity
        "retained_earnings": retained_latest,
        "share_dilution_rate": share_dilution,
        # Ownership & risk
        "insider_ownership": info.get("heldPercentInsiders"),
        "institutional_ownership": info.get("heldPercentInstitutions"),
        "beta": info.get("beta"),
        "float_shares": info.get("floatShares"),
    }
