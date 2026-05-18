"""Modul valuasi: Graham Number, Simple DCF, dan Margin of Safety.

Filosofi: kalau input tidak memadai, fungsi return None alih-alih asumsi liar.
MOS dihitung relatif terhadap intrinsic value yang dipilih user (Graham atau DCF).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class ValuationResult:
    method: str
    intrinsic_value: float | None  # per share dalam mata uang yang sama dengan harga
    margin_of_safety: float | None  # desimal, positif = undervalued
    inputs: dict[str, Any]
    notes: str = ""


def graham_number(eps: float | None, book_value_per_share: float | None) -> float | None:
    """Graham Number = sqrt(22.5 * EPS * BVPS).

    Faktor 22.5 berasal dari batas Graham: PER <= 15 dan PBV <= 1.5,
    sehingga PER * PBV <= 22.5.
    Hanya valid untuk EPS > 0 dan BVPS > 0 (perusahaan profitable, ekuitas positif).
    """
    if eps is None or book_value_per_share is None:
        return None
    if eps <= 0 or book_value_per_share <= 0:
        return None
    return math.sqrt(22.5 * eps * book_value_per_share)


def margin_of_safety(intrinsic: float | None, price: float | None) -> float | None:
    """MOS = (intrinsic - price) / intrinsic. Positif = saham undervalued."""
    if intrinsic is None or price is None or intrinsic <= 0:
        return None
    return (intrinsic - price) / intrinsic


def simple_dcf(
    free_cash_flow: float | None,
    shares_outstanding: float | None,
    growth_rate: float = 0.08,
    terminal_growth: float = 0.04,
    discount_rate: float = 0.12,
    years: int = 10,
    cash: float = 0.0,
    debt: float = 0.0,
) -> float | None:
    """DCF sederhana dua tahap menghasilkan nilai intrinsik per saham.

    Asumsi default kalibrasi konteks Indonesia (yield SBN 10Y ~7%,
    equity risk premium ~5%, jadi discount rate ~12%).

    Args:
        free_cash_flow: FCF terakhir (IDR). Wajib > 0.
        shares_outstanding: jumlah lembar saham beredar.
        growth_rate: pertumbuhan FCF tahun 1-`years` (desimal, mis. 0.10 = 10%).
        terminal_growth: pertumbuhan setelah `years` (harus < discount_rate).
        discount_rate: WACC / cost of equity (desimal).
        years: horizon proyeksi eksplisit.
        cash: kas & setara kas (ditambahkan ke equity value).
        debt: total utang (dikurangkan dari equity value).

    Returns:
        Intrinsic value per saham, atau None bila input tidak valid.
    """
    if free_cash_flow is None or shares_outstanding is None:
        return None
    if free_cash_flow <= 0 or shares_outstanding <= 0:
        return None
    if discount_rate <= terminal_growth:
        return None

    pv_explicit = 0.0
    fcf = free_cash_flow
    for year in range(1, years + 1):
        fcf = fcf * (1 + growth_rate)
        pv_explicit += fcf / ((1 + discount_rate) ** year)

    # Terminal value menggunakan Gordon Growth, didiskon balik ke present
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount_rate) ** years)

    enterprise_value = pv_explicit + pv_terminal
    equity_value = enterprise_value + (cash or 0) - (debt or 0)
    return equity_value / shares_outstanding


def intrinsic_value_summary(
    metrics: dict[str, Any],
    dcf_growth: float = 0.08,
    dcf_terminal: float = 0.04,
    dcf_discount: float = 0.12,
    dcf_years: int = 10,
) -> dict[str, ValuationResult]:
    """Hitung Graham & DCF dari hasil `compute_metrics`, plus MOS masing-masing."""
    price = metrics.get("current_price")
    eps = metrics.get("eps")
    bvps = metrics.get("book_value_per_share")
    fcf = metrics.get("free_cash_flow")
    shares = metrics.get("shares_outstanding")
    cash = metrics.get("total_debt")  # placeholder, di-overwrite di bawah
    cash = 0.0
    debt = metrics.get("total_debt") or 0.0
    # Ambil cash dari net_debt + debt
    if metrics.get("net_debt") is not None and metrics.get("total_debt") is not None:
        cash = metrics["total_debt"] - metrics["net_debt"]

    graham = graham_number(eps, bvps)
    graham_result = ValuationResult(
        method="Graham Number",
        intrinsic_value=graham,
        margin_of_safety=margin_of_safety(graham, price),
        inputs={"eps": eps, "bvps": bvps},
        notes="Hanya berlaku untuk emiten profitable dengan ekuitas positif.",
    )

    dcf = simple_dcf(
        free_cash_flow=fcf,
        shares_outstanding=shares,
        growth_rate=dcf_growth,
        terminal_growth=dcf_terminal,
        discount_rate=dcf_discount,
        years=dcf_years,
        cash=cash,
        debt=debt,
    )
    dcf_result = ValuationResult(
        method="Simple DCF",
        intrinsic_value=dcf,
        margin_of_safety=margin_of_safety(dcf, price),
        inputs={
            "fcf": fcf,
            "shares": shares,
            "growth_rate": dcf_growth,
            "terminal_growth": dcf_terminal,
            "discount_rate": dcf_discount,
            "years": dcf_years,
            "cash": cash,
            "debt": debt,
        },
        notes="DCF dua tahap. Sensitif terhadap asumsi growth & discount rate.",
    )

    return {"graham": graham_result, "dcf": dcf_result}
