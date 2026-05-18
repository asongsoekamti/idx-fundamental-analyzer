"""Scoring, valuation blending, dan verdict untuk CLI report.

Berisi:
- ``conservative_intrinsic_value``: blend Graham + DCF dengan haircut konservatif.
- ``earnings_stability_label``: konversi stdev margin -> High/Medium/Low.
- ``quality_score`` / ``valuation_score`` / ``risk_score``: 0-100 berbasis bucket.
- ``overall_verdict``: BUY / ACCUMULATE / HOLD / REDUCE / SELL.
- ``apply_quality_floor``: downgrade verdict bila ROE di bawah threshold
  (default 12%) - relevan terutama untuk saham bank.
- ``build_scorecard``: orchestrator. Otomatis pilih banking valuation (DDM+PBV)
  bila ``is_banking_stock(metrics)`` True, else pakai jalur Graham+DCF lama.

Filosofi: gunakan asumsi konservatif. Nilai None saat input tidak cukup,
biar layer presentation menampilkan ``N/A`` ketimbang skor palsu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analyzer.banking import (
    ROE_DOWNGRADE_THRESHOLD,
    banking_valuation,
    is_banking_stock,
)


# ----------------------------- Konstanta DCF default -----------------------------
# Default kalibrasi konteks IDX (SBN10Y ~7%, ERP ~5%, sehingga WACC ~12%).
# Default growth & terminal sengaja dipilih moderat-konservatif.
DEFAULT_DCF_GROWTH = 0.08
DEFAULT_DCF_TERMINAL = 0.04
DEFAULT_DCF_DISCOUNT = 0.12
DEFAULT_DCF_YEARS = 10

# Haircut tambahan saat hanya satu metode valuasi yang tersedia.
SINGLE_METHOD_HAIRCUT = 0.10  # 10%


@dataclass
class ScoreCard:
    """Kontainer ringkas hasil scoring + valuasi satu emiten.

    Field ``intrinsic_ddm`` / ``intrinsic_pbv`` / ``cost_of_equity`` /
    ``assumed_growth`` / ``assumed_payout`` hanya terisi untuk saham bank.
    Untuk non-bank field tersebut ``None``.
    """

    quality: float | None
    valuation: float | None
    risk: float | None
    composite: float | None
    verdict: str
    earnings_stability: str
    intrinsic_value: float | None
    intrinsic_method: str  # mis. "Blend (Graham+DCF)" atau "Banking Blend (50% DDM + 50% PBV)"
    mos: float | None  # margin of safety (desimal, positif = undervalued)
    upside: float | None  # (IV - price) / price

    # Banking-only breakdown (None untuk non-bank).
    is_banking: bool = False
    intrinsic_ddm: float | None = None
    intrinsic_pbv: float | None = None
    cost_of_equity: float | None = None
    assumed_growth: float | None = None
    assumed_payout: float | None = None
    pbv_fair: float | None = None
    quality_floor_applied: bool = False
    notes: list[str] = field(default_factory=list)


# ----------------------------- Helpers bucket -----------------------------

def _bucket(value: float | None, breakpoints: list[tuple[float, float]],
            higher_is_better: bool = True) -> float | None:
    """Map value -> skor 0-100 menggunakan tabel breakpoint.

    ``breakpoints`` adalah list ``(threshold, score)`` urut dari yang terbaik ke
    terburuk untuk ``higher_is_better=True``, sebaliknya untuk False.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN check tanpa import math
        return None
    for threshold, score in breakpoints:
        if higher_is_better and v >= threshold:
            return float(score)
        if (not higher_is_better) and v <= threshold:
            return float(score)
    # Tidak ada bucket yang match -> kembalikan skor terburuk dari list.
    return float(breakpoints[-1][1])


def _avg(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


# ----------------------------- Earnings stability -----------------------------

def earnings_stability_label(stdev_net_margin: float | None) -> str:
    """Konversi stdev net margin tahunan -> label High/Medium/Low.

    Threshold konservatif: net margin yang kurang fluktuatif (stdev kecil)
    menandakan business model yang lebih stabil.
    """
    if stdev_net_margin is None:
        return "N/A"
    if stdev_net_margin < 0.02:
        return "High"
    if stdev_net_margin < 0.05:
        return "Medium"
    return "Low"


def _stability_score(label: str) -> float | None:
    return {"High": 100.0, "Medium": 65.0, "Low": 35.0}.get(label)


# ----------------------------- Conservative IV blend -----------------------------

def conservative_intrinsic_value(
    graham: float | None,
    dcf: float | None,
) -> tuple[float | None, str]:
    """Blend Graham & DCF jadi satu intrinsic value moderat-konservatif.

    Aturan:
    - Kedua metode tersedia -> rata-rata sederhana (moderate).
    - Hanya satu metode -> pakai itu, dipotong ``SINGLE_METHOD_HAIRCUT``
      untuk kompensasi ketidakpastian.
    - Tidak ada -> ``None``.

    Return:
        (intrinsic_value, method_label)
    """
    have_g = graham is not None and graham > 0
    have_d = dcf is not None and dcf > 0

    if have_g and have_d:
        return (graham + dcf) / 2.0, "Blend (Graham+DCF)"
    if have_g:
        return graham * (1 - SINGLE_METHOD_HAIRCUT), "Graham (haircut 10%)"
    if have_d:
        return dcf * (1 - SINGLE_METHOD_HAIRCUT), "DCF (haircut 10%)"
    return None, "N/A"


def margin_of_safety(intrinsic: float | None, price: float | None) -> float | None:
    """MOS = (IV - price) / IV. Positif = undervalued."""
    if intrinsic is None or price is None or intrinsic <= 0:
        return None
    return (intrinsic - price) / intrinsic


def upside(intrinsic: float | None, price: float | None) -> float | None:
    """Upside = (IV - price) / price. Positif = potensi naik."""
    if intrinsic is None or price is None or price <= 0:
        return None
    return (intrinsic - price) / price


# ----------------------------- Quality / Valuation / Risk -----------------------------

def quality_score(metrics: dict[str, Any]) -> float | None:
    """Skor kualitas bisnis berdasar ROE, ROA, net margin, stabilitas margin."""
    roe = _bucket(
        metrics.get("roe"),
        [(0.20, 100), (0.15, 85), (0.10, 65), (0.05, 45), (-1e9, 25)],
        higher_is_better=True,
    )
    roa = _bucket(
        metrics.get("roa"),
        [(0.10, 100), (0.07, 85), (0.05, 65), (0.03, 45), (-1e9, 25)],
        higher_is_better=True,
    )
    net_margin = _bucket(
        metrics.get("net_margin"),
        [(0.25, 100), (0.15, 85), (0.10, 65), (0.05, 45), (-1e9, 25)],
        higher_is_better=True,
    )
    stab_label = earnings_stability_label(metrics.get("net_margin_stability_stdev"))
    stab = _stability_score(stab_label)

    parts = [roe, roa, net_margin, stab]
    avg = _avg(parts)
    if avg is None:
        return None
    return round(avg, 1)


def valuation_score(
    metrics: dict[str, Any],
    mos: float | None,
) -> float | None:
    """Skor valuasi: rendah PER/PBV/PEG dan tinggi MOS = lebih bagus."""
    per = _bucket(
        metrics.get("per"),
        [(10, 100), (15, 85), (20, 65), (25, 45), (1e9, 25)],
        higher_is_better=False,
    )
    pbv = _bucket(
        metrics.get("pbv"),
        [(1.5, 100), (2.5, 85), (4.0, 65), (6.0, 45), (1e9, 25)],
        higher_is_better=False,
    )
    peg_val = metrics.get("peg")
    # PEG negatif (akibat earnings turun) tidak bisa dipakai sebagai sinyal valuasi.
    if peg_val is not None and peg_val < 0:
        peg = 30.0  # penalti ringan, jangan no-data
    else:
        peg = _bucket(
            peg_val,
            [(1.0, 100), (1.5, 85), (2.0, 65), (3.0, 45), (1e9, 25)],
            higher_is_better=False,
        )
    mos_b = _bucket(
        mos,
        [(0.30, 100), (0.20, 85), (0.10, 65), (0.0, 45), (-1e9, 20)],
        higher_is_better=True,
    )
    parts = [per, pbv, peg, mos_b]
    avg = _avg(parts)
    if avg is None:
        return None
    return round(avg, 1)


def risk_score(metrics: dict[str, Any]) -> float | None:
    """Skor risiko (lebih tinggi = lebih aman): leverage rendah, likuiditas baik,
    bunga tertutup, beta rendah, earnings stabil.
    """
    der = _bucket(
        metrics.get("der"),
        [(0.3, 100), (0.5, 85), (1.0, 65), (2.0, 45), (1e9, 25)],
        higher_is_better=False,
    )
    cr = _bucket(
        metrics.get("current_ratio"),
        [(2.0, 100), (1.5, 85), (1.2, 65), (1.0, 45), (-1e9, 25)],
        higher_is_better=True,
    )
    ic = _bucket(
        metrics.get("interest_coverage"),
        [(10, 100), (5, 85), (3, 65), (1.5, 45), (-1e9, 25)],
        higher_is_better=True,
    )
    beta = _bucket(
        metrics.get("beta"),
        [(0.8, 100), (1.0, 85), (1.2, 65), (1.5, 45), (1e9, 25)],
        higher_is_better=False,
    )
    stab_label = earnings_stability_label(metrics.get("net_margin_stability_stdev"))
    stab = _stability_score(stab_label)

    parts = [der, cr, ic, beta, stab]
    avg = _avg(parts)
    if avg is None:
        return None
    return round(avg, 1)


# ----------------------------- Verdict -----------------------------

def apply_quality_floor(
    verdict: str,
    roe: float | None,
    threshold: float = ROE_DOWNGRADE_THRESHOLD,
) -> tuple[str, bool]:
    """Cap verdict ke HOLD bila ROE di bawah ``threshold``.

    Aturan: kualitas bisnis (proxied by ROE) yang lemah mengalahkan sinyal
    valuasi - bahkan saham yang tampak murah tidak layak BUY/ACCUMULATE
    kalau profitabilitas ekuitasnya di bawah cost of equity yang wajar.

    Default threshold 12% sesuai permintaan user (ekuilibrium kasar antara
    cost of equity untuk emiten IDX dan ROE minimum yang di-considered
    "ROE > COE" oleh value investor).

    Return:
        ``(verdict_baru, applied)`` - ``applied=True`` kalau memang di-downgrade.
    """
    if roe is None:
        return verdict, False
    try:
        if float(roe) >= threshold:
            return verdict, False
    except (TypeError, ValueError):
        return verdict, False
    if verdict in {"BUY", "ACCUMULATE"}:
        return "HOLD", True
    # Untuk verdict yang sudah di HOLD/REDUCE/SELL kita biarkan (sudah cukup
    # mencerminkan kekhawatiran).
    return verdict, False


def overall_verdict(
    quality: float | None,
    valuation: float | None,
    risk: float | None,
    mos: float | None,
) -> tuple[float | None, str]:
    """Composite (rata-rata 3 skor) + rekomendasi konservatif.

    Aturan verdict:
    - BUY        : composite >= 75 dan MOS >= 15%
    - ACCUMULATE : composite >= 65 dan MOS >= 5%
    - HOLD       : composite >= 50
    - REDUCE     : composite >= 35 atau MOS < -10%
    - SELL       : composite < 35 atau MOS < -25%
    Saat data tidak cukup -> N/A.
    """
    parts = [v for v in (quality, valuation, risk) if v is not None]
    if not parts:
        return None, "N/A"
    composite = round(sum(parts) / len(parts), 1)

    m = mos if mos is not None else 0.0

    if composite < 35 or m < -0.25:
        return composite, "SELL"
    if composite < 50 or m < -0.10:
        return composite, "REDUCE"
    if composite >= 75 and m >= 0.15:
        return composite, "BUY"
    if composite >= 65 and m >= 0.05:
        return composite, "ACCUMULATE"
    return composite, "HOLD"


# ----------------------------- Public entry -----------------------------

def build_scorecard(
    metrics: dict[str, Any],
    graham_value: float | None,
    dcf_value: float | None,
    cost_of_equity: float | None = None,
) -> ScoreCard:
    """Bangun ``ScoreCard`` lengkap.

    Pemilihan model valuasi:
    - Bila ``is_banking_stock(metrics)`` True -> gunakan ``banking_valuation``
      (DDM 50% + Justified PBV 50%). Argumen ``graham_value`` / ``dcf_value``
      diabaikan.
    - Selain itu -> blend Graham + DCF (``conservative_intrinsic_value``).

    Setelah verdict awal terhitung, ``apply_quality_floor`` dipanggil untuk
    cap ke HOLD bila ROE < 12% (regardless of MOS).
    """
    notes: list[str] = []
    is_bank = is_banking_stock(metrics)

    iv: float | None
    method: str
    intrinsic_ddm: float | None = None
    intrinsic_pbv: float | None = None
    coe: float | None = None
    growth: float | None = None
    payout: float | None = None
    pbv_fair: float | None = None

    if is_bank:
        bv = banking_valuation(metrics, cost_of_equity=cost_of_equity)
        iv = bv.intrinsic_value
        method = bv.method
        intrinsic_ddm = bv.intrinsic_ddm
        intrinsic_pbv = bv.intrinsic_pbv
        coe = bv.cost_of_equity
        growth = bv.growth
        payout = bv.payout_ratio
        pbv_fair = bv.pbv_fair
        if bv.notes:
            notes.append(bv.notes)
        notes.append("Banking sector detected -> DDM+PBV (DCF skipped).")
    else:
        iv, method = conservative_intrinsic_value(graham_value, dcf_value)

    price = metrics.get("current_price")
    mos = margin_of_safety(iv, price)
    ups = upside(iv, price)

    q = quality_score(metrics)
    v = valuation_score(metrics, mos)
    r = risk_score(metrics)
    composite, verdict = overall_verdict(q, v, r, mos)

    # Quality floor: ROE < 12% -> downgrade BUY/ACCUMULATE -> HOLD.
    verdict, downgraded = apply_quality_floor(verdict, metrics.get("roe"))
    if downgraded:
        notes.append(
            f"ROE < {ROE_DOWNGRADE_THRESHOLD * 100:.0f}% -> verdict di-cap ke HOLD."
        )

    stab_label = earnings_stability_label(metrics.get("net_margin_stability_stdev"))

    return ScoreCard(
        quality=q,
        valuation=v,
        risk=r,
        composite=composite,
        verdict=verdict,
        earnings_stability=stab_label,
        intrinsic_value=iv,
        intrinsic_method=method,
        mos=mos,
        upside=ups,
        is_banking=is_bank,
        intrinsic_ddm=intrinsic_ddm,
        intrinsic_pbv=intrinsic_pbv,
        cost_of_equity=coe,
        assumed_growth=growth,
        assumed_payout=payout,
        pbv_fair=pbv_fair,
        quality_floor_applied=downgraded,
        notes=notes,
    )
