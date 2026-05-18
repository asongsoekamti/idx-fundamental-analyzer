"""Formatter laporan teks untuk console dan TXT export.

Tidak melakukan I/O. Hanya membangun string supaya gampang di-test.
Layer ``analyzer.export`` yang nulis ke file (TXT/PDF).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from analyzer.scoring import (
    DEFAULT_DCF_DISCOUNT,
    DEFAULT_DCF_GROWTH,
    DEFAULT_DCF_TERMINAL,
    ScoreCard,
)


# ----------------------------- Formatter dasar -----------------------------

def fmt_pct(x: float | None, decimals: int = 2) -> str:
    """Format angka desimal jadi persen. ``0.235`` -> ``23.50%``."""
    if x is None:
        return "N/A"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "N/A"
    if v != v:
        return "N/A"
    return f"{v * 100:.{decimals}f}%"


def fmt_num(x: float | None, decimals: int = 2, suffix: str = "") -> str:
    if x is None:
        return "N/A"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "N/A"
    if v != v:
        return "N/A"
    return f"{v:,.{decimals}f}{suffix}"


def fmt_money(x: float | None, currency: str = "IDR") -> str:
    """Format angka jadi mata uang dengan grouping ribuan (no scaling)."""
    if x is None:
        return "N/A"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "N/A"
    if v != v:
        return "N/A"
    return f"{currency} {v:,.0f}"


def fmt_money_short(x: float | None, currency: str = "IDR") -> str:
    """Format ringkas: T (triliun) / M (miliar) / jt."""
    if x is None:
        return "N/A"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "N/A"
    abs_v = abs(v)
    if abs_v >= 1e12:
        return f"{currency} {v/1e12:,.2f} T"
    if abs_v >= 1e9:
        return f"{currency} {v/1e9:,.2f} M"
    if abs_v >= 1e6:
        return f"{currency} {v/1e6:,.2f} jt"
    return f"{currency} {v:,.0f}"


# ----------------------------- Verdict marker -----------------------------

def verdict_marker(verdict: str) -> str:
    """Tambah simbol ASCII di belakang verdict (tanpa emoji default)."""
    mapping = {
        "BUY": "[+]",
        "ACCUMULATE": "[+]",
        "HOLD": "[=]",
        "REDUCE": "[-]",
        "SELL": "[-]",
        "N/A": "[?]",
    }
    return f"{verdict} {mapping.get(verdict, '')}".strip()


# ----------------------------- Console / TXT report (per emiten) -----------------------------

@dataclass
class DcfAssumptions:
    """Asumsi DCF yang dipakai run ini, ditampilkan di section DCF Assumptions."""

    growth: float = DEFAULT_DCF_GROWTH
    terminal: float = DEFAULT_DCF_TERMINAL
    discount: float = DEFAULT_DCF_DISCOUNT


def render_stock_section(
    metrics: dict[str, Any],
    score: ScoreCard,
    dcf: DcfAssumptions,
    width: int = 64,
) -> str:
    """Bangun string blok laporan satu emiten ala contoh user.

    Output multi-line, sudah di-rapikan dengan kolom label-value, tanpa warna
    (TXT-friendly). Return cocok dipakai langsung untuk console maupun file.
    """
    lines: list[str] = []
    bar = "=" * width

    name = metrics.get("name") or ""
    ticker = metrics.get("ticker") or "N/A"
    currency = metrics.get("currency") or "IDR"

    lines.append(bar)
    title = f"Ticker: {ticker}"
    if name:
        title += f"  -  {name}"
    lines.append(title)
    sub_parts = [p for p in (metrics.get("sector"), metrics.get("industry")) if p]
    if sub_parts:
        lines.append("  ".join(sub_parts))
    lines.append(bar)

    # Header valuation
    lines.append(_kv("Price", fmt_money(metrics.get("current_price"), currency)))
    lines.append(_kv("Intrinsic Value", fmt_money(score.intrinsic_value, currency)
                     + f"  ({score.intrinsic_method})"))
    lines.append(_kv("MOS", fmt_pct(score.mos)))
    lines.append(_kv("Upside", fmt_pct(score.upside)))

    # Banking-specific breakdown: DDM IV + Justified PBV IV.
    if score.is_banking:
        lines.append("")
        lines.append("--- Banking Valuation Breakdown ---")
        lines.append(_kv("DDM IV", fmt_money(score.intrinsic_ddm, currency)))
        lines.append(_kv("Justified PBV IV", fmt_money(score.intrinsic_pbv, currency)))
        lines.append(_kv("Justified PBV Multiple", fmt_num(score.pbv_fair, 2, "x")))

    # Profitability
    lines.append("")
    lines.append("--- Profitability ---")
    lines.append(_kv("ROE", fmt_pct(metrics.get("roe"))))
    lines.append(_kv("ROA", fmt_pct(metrics.get("roa"))))
    lines.append(_kv("Net Margin", fmt_pct(metrics.get("net_margin"))))
    lines.append(_kv("Operating Margin", fmt_pct(metrics.get("operating_margin"))))

    # Growth
    lines.append("")
    lines.append("--- Growth ---")
    lines.append(_kv("Revenue Growth (YoY)", fmt_pct(metrics.get("revenue_growth_yoy"))))
    lines.append(_kv("Net Income Growth (YoY)", fmt_pct(metrics.get("earnings_growth_yoy"))))
    lines.append(_kv("Revenue CAGR 5Y", fmt_pct(metrics.get("revenue_cagr_5y"))))
    fcf_growth = metrics.get("revenue_cagr_5y")  # proxy bila history FCF tidak ada
    lines.append(_kv("FCF Growth (proxy 5Y)", fmt_pct(fcf_growth)))

    # Valuation
    lines.append("")
    lines.append("--- Valuation ---")
    lines.append(_kv("PER", fmt_num(metrics.get("per"), 2, "x")))
    lines.append(_kv("PBV", fmt_num(metrics.get("pbv"), 2, "x")))
    lines.append(_kv("PEG", fmt_num(metrics.get("peg"), 2)))
    p_fcf = _safe_div(metrics.get("market_cap"), metrics.get("free_cash_flow"))
    lines.append(_kv("Price/FCF", fmt_num(p_fcf, 2, "x")))

    # Financial Health
    lines.append("")
    lines.append("--- Financial Health ---")
    lines.append(_kv("DER", fmt_num(metrics.get("der"), 2)))
    lines.append(_kv("Interest Coverage", fmt_num(metrics.get("interest_coverage"), 2, "x")))
    lines.append(_kv("Current Ratio", fmt_num(metrics.get("current_ratio"), 2)))

    # Risk
    lines.append("")
    lines.append("--- Risk ---")
    lines.append(_kv("Beta", fmt_num(metrics.get("beta"), 2)))
    lines.append(_kv("Earnings Stability", score.earnings_stability))

    # Valuation Assumptions (banking-aware)
    lines.append("")
    if score.is_banking:
        lines.append("--- Banking Valuation Assumptions ---")
        lines.append(_kv("Cost of Equity", fmt_pct(score.cost_of_equity, 1)))
        lines.append(_kv("Implied Growth", fmt_pct(score.assumed_growth, 1)))
        lines.append(_kv("Payout Ratio", fmt_pct(score.assumed_payout, 1)))
        lines.append(_kv("Model", "DDM 50% + Justified PBV 50%"))
    else:
        lines.append("--- DCF Assumptions ---")
        lines.append(_kv("WACC (discount)", fmt_pct(dcf.discount, 1)))
        lines.append(_kv("Growth (10Y)", fmt_pct(dcf.growth, 1)))
        lines.append(_kv("Terminal Growth", fmt_pct(dcf.terminal, 1)))

    # Score
    lines.append("")
    lines.append("--- Score ---")
    lines.append(_kv("Quality Score", fmt_num(score.quality, 1, " / 100")))
    lines.append(_kv("Valuation Score", fmt_num(score.valuation, 1, " / 100")))
    lines.append(_kv("Risk Score", fmt_num(score.risk, 1, " / 100")))
    composite_str = fmt_num(score.composite, 1) if score.composite is not None else "N/A"
    lines.append(_kv("Composite", composite_str))
    lines.append(_kv("Overall", verdict_marker(score.verdict)))
    if score.quality_floor_applied:
        lines.append(_kv("Note", "Verdict di-cap (ROE < 12% quality floor)"))
    lines.append("")

    return "\n".join(lines)


def _kv(label: str, value: str, label_width: int = 22) -> str:
    return f"{label:<{label_width}} : {value}"


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    try:
        d = float(den)
        if d == 0:
            return None
        return float(num) / d
    except (TypeError, ValueError):
        return None


# ----------------------------- ASCII summary table -----------------------------

SUMMARY_HEADERS = [
    "Ticker", "Price", "IV", "MOS", "Upside",
    "ROE", "PER", "PBV", "DER", "Score", "Verdict",
]


def build_summary_rows(
    items: Iterable[tuple[dict[str, Any], ScoreCard]],
) -> list[list[str]]:
    """Bangun list-of-list (string) untuk dirender sebagai tabel ringkas."""
    rows: list[list[str]] = []
    for metrics, sc in items:
        currency = metrics.get("currency") or "IDR"
        rows.append([
            str(metrics.get("ticker") or "N/A"),
            fmt_money(metrics.get("current_price"), currency),
            fmt_money(sc.intrinsic_value, currency),
            fmt_pct(sc.mos, 1),
            fmt_pct(sc.upside, 1),
            fmt_pct(metrics.get("roe"), 1),
            fmt_num(metrics.get("per"), 2),
            fmt_num(metrics.get("pbv"), 2),
            fmt_num(metrics.get("der"), 2),
            fmt_num(sc.composite, 1) if sc.composite is not None else "N/A",
            sc.verdict,
        ])
    return rows


def render_ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    """Tabel ASCII sederhana dengan border ``+``/``-``/``|``.

    Rapi untuk dilihat di terminal monospaced dan di file TXT.
    """
    if not rows:
        rows = [[""] * len(headers)]
    cols = list(zip(headers, *rows))
    widths = [max(len(str(cell)) for cell in col) for col in cols]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def _fmt_row(row: list[str]) -> str:
        cells = [f" {str(cell):<{widths[i]}} " for i, cell in enumerate(row)]
        return "|" + "|".join(cells) + "|"

    lines = [sep, _fmt_row(headers), sep]
    for r in rows:
        lines.append(_fmt_row(r))
    lines.append(sep)
    return "\n".join(lines)


# ----------------------------- Per-stock detail rows (untuk PDF table) -----------------------------

def build_detail_rows(
    metrics: dict[str, Any],
    score: ScoreCard,
    dcf: DcfAssumptions,
) -> list[tuple[str, str, str]]:
    """Return list ``(group, metric, value)`` untuk dipakai di PDF/TXT detail tabel.

    Group ``Valuation Assumptions`` adaptif:
    - Banking -> Cost of Equity, Implied Growth, Payout Ratio, Model.
    - Non-banking -> WACC, Growth (10Y), Terminal Growth.
    """
    currency = metrics.get("currency") or "IDR"
    p_fcf = _safe_div(metrics.get("market_cap"), metrics.get("free_cash_flow"))

    rows: list[tuple[str, str, str]] = [
        ("Identity", "Ticker", str(metrics.get("ticker") or "N/A")),
        ("Identity", "Name", str(metrics.get("name") or "")),
        ("Identity", "Sector", str(metrics.get("sector") or "")),
        ("Identity", "Industry", str(metrics.get("industry") or "")),
        ("Identity", "Banking?", "Yes" if score.is_banking else "No"),

        ("Valuation", "Price", fmt_money(metrics.get("current_price"), currency)),
        ("Valuation", "Intrinsic Value", fmt_money(score.intrinsic_value, currency)),
        ("Valuation", "IV Method", score.intrinsic_method),
        ("Valuation", "MOS", fmt_pct(score.mos)),
        ("Valuation", "Upside", fmt_pct(score.upside)),
    ]

    # Banking-only rows: tampilkan DDM/PBV breakdown.
    if score.is_banking:
        rows.extend([
            ("Banking Valuation", "DDM IV", fmt_money(score.intrinsic_ddm, currency)),
            ("Banking Valuation", "Justified PBV IV", fmt_money(score.intrinsic_pbv, currency)),
            ("Banking Valuation", "Justified PBV Multiple",
             fmt_num(score.pbv_fair, 2, "x")),
        ])

    rows.extend([
        ("Profitability", "ROE", fmt_pct(metrics.get("roe"))),
        ("Profitability", "ROA", fmt_pct(metrics.get("roa"))),
        ("Profitability", "Net Margin", fmt_pct(metrics.get("net_margin"))),
        ("Profitability", "Operating Margin", fmt_pct(metrics.get("operating_margin"))),

        ("Growth", "Revenue Growth (YoY)", fmt_pct(metrics.get("revenue_growth_yoy"))),
        ("Growth", "Net Income Growth (YoY)", fmt_pct(metrics.get("earnings_growth_yoy"))),
        ("Growth", "Revenue CAGR 5Y", fmt_pct(metrics.get("revenue_cagr_5y"))),

        ("Valuation Ratio", "PER", fmt_num(metrics.get("per"), 2, "x")),
        ("Valuation Ratio", "PBV", fmt_num(metrics.get("pbv"), 2, "x")),
        ("Valuation Ratio", "PEG", fmt_num(metrics.get("peg"), 2)),
        ("Valuation Ratio", "Price/FCF", fmt_num(p_fcf, 2, "x")),

        ("Financial Health", "DER", fmt_num(metrics.get("der"), 2)),
        ("Financial Health", "Interest Coverage", fmt_num(metrics.get("interest_coverage"), 2, "x")),
        ("Financial Health", "Current Ratio", fmt_num(metrics.get("current_ratio"), 2)),

        ("Risk", "Beta", fmt_num(metrics.get("beta"), 2)),
        ("Risk", "Earnings Stability", score.earnings_stability),
    ])

    # Valuation assumptions group (adaptif banking vs non-banking).
    if score.is_banking:
        rows.extend([
            ("Valuation Assumptions", "Model", "DDM 50% + Justified PBV 50%"),
            ("Valuation Assumptions", "Cost of Equity", fmt_pct(score.cost_of_equity, 1)),
            ("Valuation Assumptions", "Implied Growth", fmt_pct(score.assumed_growth, 1)),
            ("Valuation Assumptions", "Payout Ratio", fmt_pct(score.assumed_payout, 1)),
        ])
    else:
        rows.extend([
            ("Valuation Assumptions", "Model", "Graham 50% + DCF 50%"),
            ("Valuation Assumptions", "WACC", fmt_pct(dcf.discount, 1)),
            ("Valuation Assumptions", "Growth (10Y)", fmt_pct(dcf.growth, 1)),
            ("Valuation Assumptions", "Terminal Growth", fmt_pct(dcf.terminal, 1)),
        ])

    rows.extend([
        ("Score", "Quality", fmt_num(score.quality, 1, " / 100")),
        ("Score", "Valuation", fmt_num(score.valuation, 1, " / 100")),
        ("Score", "Risk", fmt_num(score.risk, 1, " / 100")),
        ("Score", "Composite", fmt_num(score.composite, 1) if score.composite is not None else "N/A"),
        ("Score", "Verdict", score.verdict),
        ("Score", "Quality Floor", "Applied (ROE < 12%)" if score.quality_floor_applied else "Not applied"),
    ])
    return rows


DISCLAIMER_TEXT = (
    "DISCLAIMER: Tool ini hanya untuk edukasi/riset pribadi. "
    "Data dari Yahoo Finance bisa delay atau tidak lengkap. "
    "Bukan rekomendasi beli/jual. Selalu cross-check ke laporan resmi IDX."
)
