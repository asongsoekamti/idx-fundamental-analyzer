"""Streamlit dashboard - IDX Fundamental Analyzer.

Jalankan dari root folder project:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analyzer.fetcher import StockFetcher, normalize_ticker
from analyzer.metrics import compute_metrics
from analyzer.screener import load_watchlist, screen_watchlist
from analyzer.valuation import intrinsic_value_summary


st.set_page_config(
    page_title="IDX Fundamental Analyzer",
    page_icon="ID",
    layout="wide",
)


# -------------------------- Helper formatters --------------------------

def fmt_pct(x):
    if x is None or pd.isna(x):
        return "N/A"
    return f"{x*100:.2f}%"


def fmt_num(x, decimals=2):
    if x is None or pd.isna(x):
        return "N/A"
    return f"{x:,.{decimals}f}"


def fmt_money(x, currency="IDR"):
    if x is None or pd.isna(x):
        return "N/A"
    abs_x = abs(x)
    if abs_x >= 1e12:
        return f"{currency} {x/1e12:.2f} T"
    if abs_x >= 1e9:
        return f"{currency} {x/1e9:.2f} M"
    if abs_x >= 1e6:
        return f"{currency} {x/1e6:.2f} jt"
    return f"{currency} {x:,.0f}"


@st.cache_resource
def get_fetcher(cache_ttl: int) -> StockFetcher:
    return StockFetcher(cache_ttl=cache_ttl)


# -------------------------- Sidebar --------------------------

st.sidebar.title("IDX Fundamental Analyzer")
st.sidebar.caption("Sumber data: Yahoo Finance (.JK)")

mode = st.sidebar.radio(
    "Mode",
    options=["Single Stock", "Watchlist Screener"],
    index=0,
)

st.sidebar.divider()
st.sidebar.subheader("Asumsi DCF")
dcf_growth = st.sidebar.slider("Growth FCF 10 tahun (%)", 0, 25, 8) / 100
dcf_terminal = st.sidebar.slider("Terminal growth (%)", 0, 8, 4) / 100
dcf_discount = st.sidebar.slider("Discount rate / WACC (%)", 6, 20, 12) / 100
dcf_years = st.sidebar.slider("Horizon (tahun)", 5, 15, 10)

st.sidebar.divider()
cache_hours = st.sidebar.slider("Cache TTL (jam)", 1, 24, 6)
if st.sidebar.button("Clear cache", use_container_width=True):
    st.cache_resource.clear()
    cache_dir = Path("data/cache")
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            try:
                f.unlink()
            except Exception:
                pass
    st.sidebar.success("Cache dibersihkan")

fetcher = get_fetcher(cache_ttl=cache_hours * 3600)


# -------------------------- Single Stock View --------------------------

def render_single_stock():
    st.title("Analisis Satu Emiten")
    col1, col2 = st.columns([3, 1])
    with col1:
        ticker_input = st.text_input(
            "Kode saham IDX",
            value="BBCA",
            help="Tulis BBCA atau BBCA.JK. Otomatis ditambahkan .JK kalau tidak ada.",
        )
    with col2:
        st.write("")
        st.write("")
        run = st.button("Analisis", type="primary", use_container_width=True)

    if not run and "last_ticker" not in st.session_state:
        st.info("Masukkan kode saham lalu klik Analisis.")
        return

    if run:
        st.session_state.last_ticker = normalize_ticker(ticker_input)

    ticker = st.session_state.get("last_ticker")
    if not ticker:
        return

    with st.spinner(f"Mengambil data {ticker} ..."):
        try:
            data = fetcher.fetch(ticker)
            metrics = compute_metrics(data)
        except Exception as e:
            st.error(f"Gagal fetch {ticker}: {e}")
            return

    if not metrics.get("name") and not metrics.get("current_price"):
        st.warning(
            f"Data {ticker} kosong. Cek ulang kode emiten "
            "atau coba klik Clear cache di sidebar."
        )
        return

    # Header info
    st.subheader(f"{metrics.get('name') or ticker}  ·  {ticker}")
    sub = []
    if metrics.get("sector"):
        sub.append(metrics["sector"])
    if metrics.get("industry"):
        sub.append(metrics["industry"])
    if sub:
        st.caption(" · ".join(sub))

    currency = metrics.get("currency", "IDR")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Harga", fmt_money(metrics.get("current_price"), currency))
    c2.metric("Market Cap", fmt_money(metrics.get("market_cap"), currency))
    c3.metric("PER (TTM)", fmt_num(metrics.get("per")))
    c4.metric("PBV", fmt_num(metrics.get("pbv")))

    st.divider()

    # ---------------- Valuasi & MOS ----------------
    st.subheader("Valuasi Intrinsik & Margin of Safety")
    val = intrinsic_value_summary(
        metrics,
        dcf_growth=dcf_growth,
        dcf_terminal=dcf_terminal,
        dcf_discount=dcf_discount,
        dcf_years=dcf_years,
    )
    g = val["graham"]
    d = val["dcf"]

    v1, v2 = st.columns(2)
    with v1:
        st.markdown("**Graham Number**")
        st.metric(
            label="Intrinsic Value / lembar",
            value=fmt_money(g.intrinsic_value, currency),
            delta=fmt_pct(g.margin_of_safety) + " MOS" if g.margin_of_safety is not None else "MOS N/A",
        )
        st.caption(g.notes)
    with v2:
        st.markdown("**Simple DCF (10Y)**")
        st.metric(
            label="Intrinsic Value / lembar",
            value=fmt_money(d.intrinsic_value, currency),
            delta=fmt_pct(d.margin_of_safety) + " MOS" if d.margin_of_safety is not None else "MOS N/A",
        )
        st.caption(
            f"Growth {dcf_growth*100:.0f}% / Terminal {dcf_terminal*100:.0f}% / Discount {dcf_discount*100:.0f}%"
        )

    # Chart perbandingan harga vs intrinsic
    if metrics.get("current_price"):
        fig = go.Figure()
        labels = ["Harga Pasar"]
        values = [metrics["current_price"]]
        if g.intrinsic_value:
            labels.append("Graham IV")
            values.append(g.intrinsic_value)
        if d.intrinsic_value:
            labels.append("DCF IV")
            values.append(d.intrinsic_value)
        fig.add_trace(go.Bar(x=labels, y=values, text=[fmt_money(v, currency) for v in values], textposition="auto"))
        fig.update_layout(height=300, showlegend=False, title="Harga vs Intrinsic Value")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---------------- Rasio kunci (fokus user) ----------------
    st.subheader("Rasio Fokus: ROE / ROA / PEG / PBV / MOS")
    k = st.columns(5)
    k[0].metric("ROE", fmt_pct(metrics.get("roe")))
    k[1].metric("ROA", fmt_pct(metrics.get("roa")))
    k[2].metric("PEG", fmt_num(metrics.get("peg")))
    k[3].metric("PBV", fmt_num(metrics.get("pbv")))
    k[4].metric("MOS (Graham)", fmt_pct(g.margin_of_safety))

    st.divider()

    # ---------------- Tabel lengkap (grouped) ----------------
    st.subheader("Semua Metrik")

    groups = {
        "Profitabilitas": [
            ("Revenue", fmt_money(metrics.get("revenue"), currency)),
            ("Gross Profit", fmt_money(metrics.get("gross_profit"), currency)),
            ("Operating Profit", fmt_money(metrics.get("operating_profit"), currency)),
            ("Net Profit", fmt_money(metrics.get("net_profit"), currency)),
            ("EBITDA", fmt_money(metrics.get("ebitda"), currency)),
            ("EPS", fmt_num(metrics.get("eps"))),
            ("Forward EPS", fmt_num(metrics.get("forward_eps"))),
            ("Gross Margin", fmt_pct(metrics.get("gross_margin"))),
            ("Operating Margin", fmt_pct(metrics.get("operating_margin"))),
            ("Net Margin", fmt_pct(metrics.get("net_margin"))),
            ("EBITDA Margin", fmt_pct(metrics.get("ebitda_margin"))),
            ("Cash Flow Margin", fmt_pct(metrics.get("cash_flow_margin"))),
        ],
        "Return": [
            ("ROA", fmt_pct(metrics.get("roa"))),
            ("ROE", fmt_pct(metrics.get("roe"))),
            ("ROIC", fmt_pct(metrics.get("roic"))),
            ("ROI (proxy)", fmt_pct(metrics.get("roi"))),
        ],
        "Valuasi Pasar": [
            ("Market Cap", fmt_money(metrics.get("market_cap"), currency)),
            ("Enterprise Value", fmt_money(metrics.get("enterprise_value"), currency)),
            ("PER", fmt_num(metrics.get("per"))),
            ("Forward PER", fmt_num(metrics.get("forward_per"))),
            ("PBV", fmt_num(metrics.get("pbv"))),
            ("PSR", fmt_num(metrics.get("psr"))),
            ("PEG", fmt_num(metrics.get("peg"))),
            ("EV/EBITDA", fmt_num(metrics.get("ev_ebitda"))),
            ("EV/Sales", fmt_num(metrics.get("ev_sales"))),
            ("Book Value / Share", fmt_money(metrics.get("book_value_per_share"), currency)),
            ("Tangible BV / Share", fmt_money(metrics.get("tangible_book_value_per_share"), currency)),
        ],
        "Dividen": [
            ("Dividend Yield", fmt_pct(metrics.get("dividend_yield"))),
            ("Payout Ratio", fmt_pct(metrics.get("payout_ratio"))),
            ("Dividend Rate", fmt_money(metrics.get("dividend_rate"), currency)),
        ],
        "Cash Flow": [
            ("Operating Cash Flow", fmt_money(metrics.get("operating_cash_flow"), currency)),
            ("Free Cash Flow", fmt_money(metrics.get("free_cash_flow"), currency)),
            ("CapEx", fmt_money(metrics.get("capex"), currency)),
            ("CapEx to Revenue", fmt_pct(metrics.get("capex_to_revenue"))),
        ],
        "Likuiditas": [
            ("Current Ratio", fmt_num(metrics.get("current_ratio"))),
            ("Quick Ratio", fmt_num(metrics.get("quick_ratio"))),
            ("Cash Ratio", fmt_num(metrics.get("cash_ratio"))),
            ("Working Capital", fmt_money(metrics.get("working_capital"), currency)),
            ("Working Capital Ratio", fmt_pct(metrics.get("working_capital_ratio"))),
        ],
        "Leverage": [
            ("DER", fmt_num(metrics.get("der"))),
            ("Debt to Asset", fmt_num(metrics.get("debt_to_asset"))),
            ("Total Debt", fmt_money(metrics.get("total_debt"), currency)),
            ("Net Debt", fmt_money(metrics.get("net_debt"), currency)),
            ("Net Debt / EBITDA", fmt_num(metrics.get("net_debt_to_ebitda"))),
            ("Interest Coverage", fmt_num(metrics.get("interest_coverage"))),
        ],
        "Pertumbuhan": [
            ("Revenue Growth YoY", fmt_pct(metrics.get("revenue_growth_yoy"))),
            ("Earnings Growth YoY", fmt_pct(metrics.get("earnings_growth_yoy"))),
            ("EPS Growth", fmt_pct(metrics.get("eps_growth"))),
            ("Operating Income Growth", fmt_pct(metrics.get("operating_income_growth"))),
            ("Asset Growth", fmt_pct(metrics.get("asset_growth"))),
            ("Equity Growth", fmt_pct(metrics.get("equity_growth"))),
            ("Revenue CAGR 3Y", fmt_pct(metrics.get("revenue_cagr_3y"))),
            ("Revenue CAGR 5Y", fmt_pct(metrics.get("revenue_cagr_5y"))),
            ("Net Income CAGR 3Y", fmt_pct(metrics.get("net_income_cagr_3y"))),
        ],
        "Efisiensi Operasi": [
            ("Asset Turnover", fmt_num(metrics.get("asset_turnover"))),
            ("Inventory Turnover", fmt_num(metrics.get("inventory_turnover"))),
            ("Receivable Turnover", fmt_num(metrics.get("receivable_turnover"))),
            ("Payable Turnover", fmt_num(metrics.get("payable_turnover"))),
            ("DSO (hari)", fmt_num(metrics.get("dso"), 0)),
            ("DIO (hari)", fmt_num(metrics.get("dio"), 0)),
            ("DPO (hari)", fmt_num(metrics.get("dpo"), 0)),
            ("Cash Conversion Cycle (hari)", fmt_num(metrics.get("cash_conversion_cycle"), 0)),
        ],
        "Struktur Biaya": [
            ("SG&A Ratio", fmt_pct(metrics.get("sga_ratio"))),
            ("Operating Expense Ratio", fmt_pct(metrics.get("opex_ratio"))),
            ("R&D to Revenue", fmt_pct(metrics.get("rnd_to_revenue"))),
        ],
        "Konsistensi & Risiko": [
            ("Net Margin Stability (stdev)", fmt_num(metrics.get("net_margin_stability_stdev"), 4)),
            ("Margin Expansion Trend", fmt_pct(metrics.get("margin_expansion_trend"))),
            ("Beta", fmt_num(metrics.get("beta"))),
            ("Insider Ownership", fmt_pct(metrics.get("insider_ownership"))),
            ("Institutional Ownership", fmt_pct(metrics.get("institutional_ownership"))),
            ("Share Dilution Rate", fmt_pct(metrics.get("share_dilution_rate"))),
        ],
    }

    cols = st.columns(2)
    for idx, (group_name, items) in enumerate(groups.items()):
        with cols[idx % 2]:
            with st.expander(group_name, expanded=(group_name in {"Profitabilitas", "Return"})):
                df = pd.DataFrame(items, columns=["Metrik", "Nilai"])
                st.dataframe(df, hide_index=True, use_container_width=True)

    # ---------------- Chart historis ----------------
    if not data.history.empty:
        st.divider()
        st.subheader("Harga 5 Tahun Terakhir")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.history.index, y=data.history["Close"], mode="lines", name="Close"))
        fig.update_layout(height=350, xaxis_title="Tanggal", yaxis_title=f"Harga ({currency})")
        st.plotly_chart(fig, use_container_width=True)

    # ---------------- Export ----------------
    st.divider()
    flat_df = pd.DataFrame([metrics])
    csv = flat_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download semua metrik (CSV)",
        csv,
        file_name=f"{ticker.replace('.','_')}_metrics.csv",
        mime="text/csv",
    )


# -------------------------- Watchlist Screener View --------------------------

def render_screener():
    st.title("Watchlist Screener")
    st.write(
        "Tempel daftar ticker (satu per baris) atau upload CSV dengan kolom `ticker`."
    )

    default_wl = Path("examples/watchlist.csv")
    default_text = ""
    if default_wl.exists():
        try:
            tickers = load_watchlist(default_wl)
            default_text = "\n".join(tickers)
        except Exception:
            default_text = ""

    col1, col2 = st.columns([3, 1])
    with col1:
        text = st.text_area("Watchlist", value=default_text, height=220)
    with col2:
        uploaded = st.file_uploader("Atau upload CSV", type=["csv"])
        if uploaded is not None:
            df = pd.read_csv(uploaded)
            if "ticker" in df.columns:
                text = "\n".join(str(t) for t in df["ticker"].dropna().tolist())
                st.success(f"Memuat {len(df)} ticker dari CSV")
        run = st.button("Jalankan Screener", type="primary", use_container_width=True)

    tickers = [t.strip() for t in text.splitlines() if t.strip() and not t.startswith("#")]

    if run and tickers:
        progress = st.progress(0.0, text="Memulai ...")
        def cb(i, total, ticker):
            progress.progress(i / total, text=f"[{i}/{total}] {ticker}")
        df = screen_watchlist(tickers, fetcher=fetcher, progress_callback=cb)
        progress.empty()
        st.session_state.screener_df = df

    df = st.session_state.get("screener_df")
    if df is None or df.empty:
        st.info("Klik 'Jalankan Screener' untuk memulai analisis batch.")
        return

    st.subheader(f"Hasil ({len(df)} emiten)")

    # Filter
    f1, f2, f3, f4 = st.columns(4)
    min_roe = f1.number_input("ROE min (%)", value=0.0, step=1.0)
    max_per = f2.number_input("PER max", value=0.0, step=1.0, help="0 = tanpa filter")
    max_pbv = f3.number_input("PBV max", value=0.0, step=0.1, help="0 = tanpa filter")
    min_mos = f4.number_input("MOS Graham min (%)", value=0.0, step=5.0, help="0 = tanpa filter")

    filtered = df.copy()
    if min_roe > 0:
        filtered = filtered[filtered["roe"].fillna(0) >= min_roe / 100]
    if max_per > 0:
        filtered = filtered[filtered["per"].fillna(1e9) <= max_per]
    if max_pbv > 0:
        filtered = filtered[filtered["pbv"].fillna(1e9) <= max_pbv]
    if min_mos > 0:
        filtered = filtered[filtered["mos_graham"].fillna(-1) >= min_mos / 100]

    # Pretty display
    display = filtered.copy()
    for col in ["roe", "roa", "roic", "dividend_yield", "revenue_growth_yoy", "earnings_growth_yoy", "mos_graham"]:
        if col in display:
            display[col] = display[col].apply(fmt_pct)
    for col in ["per", "pbv", "peg", "der"]:
        if col in display:
            display[col] = display[col].apply(fmt_num)
    for col in ["current_price", "graham_value"]:
        if col in display:
            display[col] = display[col].apply(lambda v: fmt_money(v))
    if "market_cap" in display:
        display["market_cap"] = display["market_cap"].apply(lambda v: fmt_money(v))

    st.dataframe(display, hide_index=True, use_container_width=True)

    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download hasil screener (CSV)",
        csv,
        file_name="idx_screener.csv",
        mime="text/csv",
    )


# -------------------------- Router --------------------------

if mode == "Single Stock":
    render_single_stock()
else:
    render_screener()

st.sidebar.divider()
st.sidebar.caption(
    "Disclaimer: Tool ini hanya untuk edukasi/riset pribadi. "
    "Data dari Yahoo Finance bisa delay atau tidak lengkap. "
    "Bukan rekomendasi beli/jual."
)
