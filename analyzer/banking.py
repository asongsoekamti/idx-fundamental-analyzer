"""Valuasi khusus saham perbankan.

Bank punya struktur cash flow yang fundamental berbeda: ``capex`` mereka
sebagian besar adalah deposit/loans (bukan investasi PP&E), sehingga FCF DCF
cenderung mis-leading dan sering memberi intrinsic value yang terlalu rendah.
Modul ini memakai pendekatan yang lazim di textbook (Damodaran):

1. **Dividend Discount Model (DDM)** - Gordon Growth:

       intrinsic_ddm = DPS / (cost_of_equity - growth)

2. **Justified P/BV** - turunan dari DDM dengan growth dari ROE:

       pbv_fair      = (ROE - growth) / (cost_of_equity - growth)
       intrinsic_pbv = pbv_fair * BVPS

3. **Final intrinsic** = blend 50/50 dari keduanya, dengan fallback ke satu
   metode bila yang lain tidak bisa dihitung.

Asumsi default kalibrasi konteks IDX:

- ``cost_of_equity`` default = 10% (bisa dioverride lewat CLI ``--coe``).
- ``growth`` = ``min(ROE * (1 - payout), 0.10)`` (cap eksplisit oleh user).
- ``payout_ratio`` default = 40% kalau yfinance tidak menyediakan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ----------------------------- Konstanta default -----------------------------

DEFAULT_COST_OF_EQUITY = 0.10
DEFAULT_PAYOUT_RATIO = 0.40
GROWTH_CAP = 0.10  # cap pertumbuhan dividen jangka panjang
ROE_DOWNGRADE_THRESHOLD = 0.12  # < 12% -> downgrade verdict regardless of MOS

# Detector sektor: yfinance memakai berbagai variasi label, jadi kita scan
# field sector + industry case-insensitive.
_BANK_KEYWORDS = (
    "bank",
    "banking",
    "thrift",
    "savings & loan",
)


# ----------------------------- Detector -----------------------------

def is_banking_stock(metrics: dict[str, Any]) -> bool:
    """Deteksi saham bank dari kombinasi sector + industry yfinance.

    Examples (yfinance):
    - BBCA.JK: sector="Financial Services", industry="Banks - Regional"
    - BBRI.JK: sector="Financial Services", industry="Banks - Regional"
    - BMRI.JK: sector="Financial Services", industry="Banks - Diversified"
    - BBNI.JK: sector="Financial Services", industry="Banks - Regional"

    Bukan bank meski di Financial Services: insurance, securities, asset mgr,
    fintech - jadi kita cocokkan ke kata kunci yang spesifik bank.
    """
    if not metrics:
        return False
    haystack = " ".join(
        str(metrics.get(field) or "").lower()
        for field in ("sector", "industry", "industry_disp")
    )
    return any(kw in haystack for kw in _BANK_KEYWORDS)


# ----------------------------- Result container -----------------------------

@dataclass
class BankingValuationResult:
    """Hasil valuasi banking. Semua nilai per share, dalam mata uang yang sama
    dengan harga (untuk IDX biasanya IDR).
    """

    intrinsic_ddm: float | None
    intrinsic_pbv: float | None
    intrinsic_value: float | None  # blended (50/50) atau fallback
    pbv_fair: float | None  # multiple, bukan harga per share
    growth: float
    cost_of_equity: float
    payout_ratio: float
    dps_used: float | None  # DPS yang dipakai (bisa di-derive dari EPS * payout)
    method: str  # label untuk ditampilkan, mis. "Banking Blend (DDM+PBV)"
    notes: str = ""


# ----------------------------- Helpers -----------------------------

def _compute_growth(roe: float | None, payout: float) -> float:
    """g = min(ROE * (1 - payout), GROWTH_CAP). Kalau ROE missing/negatif,
    return 0 supaya formula DDM tetap aman.
    """
    if roe is None:
        return 0.0
    raw = roe * (1.0 - payout)
    if raw < 0:
        return 0.0
    return min(raw, GROWTH_CAP)


def _resolve_dps(metrics: dict[str, Any], payout: float) -> float | None:
    """DPS = ``dividend_rate`` (yfinance: annualized cash dividend per share).

    Fallback: ``EPS * payout_ratio`` kalau dividend_rate tidak tersedia
    (mis. emiten tidak rutin bagi dividen tapi punya earnings positif).
    Return None kalau semua sumber kosong/tidak valid.
    """
    dr = metrics.get("dividend_rate")
    try:
        if dr is not None and float(dr) > 0:
            return float(dr)
    except (TypeError, ValueError):
        pass

    eps = metrics.get("eps")
    try:
        if eps is not None and float(eps) > 0 and payout > 0:
            return float(eps) * payout
    except (TypeError, ValueError):
        pass
    return None


# ----------------------------- Public valuation -----------------------------

def banking_valuation(
    metrics: dict[str, Any],
    cost_of_equity: float | None = None,
) -> BankingValuationResult:
    """Hitung intrinsic value untuk saham bank: DDM + Justified PBV blend.

    Parameter
    ---------
    metrics : dict hasil ``compute_metrics`` (butuh ``roe``, ``payout_ratio``,
        ``book_value_per_share``, dan salah satu dari ``dividend_rate``/``eps``).
    cost_of_equity : COE (desimal). Default ``DEFAULT_COST_OF_EQUITY`` = 10%.

    Aturan defensive:
    - ``payout_ratio`` None -> ``DEFAULT_PAYOUT_RATIO`` (40%).
    - ``cost_of_equity <= growth`` -> formula tidak terdefinisi, return None
      untuk komponen terkait (Gordon hanya valid kalau ``r > g``).
    - ``intrinsic_pbv`` hanya valid kalau ``ROE > growth`` dan ``BVPS > 0``.
    - Bila kedua komponen None -> ``intrinsic_value`` None dengan ``notes``.
    """
    coe = cost_of_equity if cost_of_equity is not None else DEFAULT_COST_OF_EQUITY

    raw_payout = metrics.get("payout_ratio")
    try:
        payout = float(raw_payout) if raw_payout is not None else DEFAULT_PAYOUT_RATIO
    except (TypeError, ValueError):
        payout = DEFAULT_PAYOUT_RATIO
    # Sanity guard: yfinance kadang return >1 (mis. emiten payout di atas EPS),
    # atau negatif. Clip ke [0, 1] supaya growth tidak negatif aneh.
    payout = max(0.0, min(payout, 1.0))

    roe = metrics.get("roe")
    try:
        roe_f: float | None = float(roe) if roe is not None else None
    except (TypeError, ValueError):
        roe_f = None

    bvps = metrics.get("book_value_per_share")
    try:
        bvps_f: float | None = float(bvps) if bvps is not None else None
    except (TypeError, ValueError):
        bvps_f = None

    growth = _compute_growth(roe_f, payout)
    dps = _resolve_dps(metrics, payout)

    # ---- DDM ----
    if dps is None or dps <= 0 or coe <= growth:
        intrinsic_ddm: float | None = None
    else:
        intrinsic_ddm = dps / (coe - growth)

    # ---- Justified PBV ----
    pbv_fair: float | None = None
    intrinsic_pbv: float | None = None
    if (
        roe_f is not None
        and bvps_f is not None
        and bvps_f > 0
        and coe > growth
        and roe_f > growth
    ):
        pbv_fair = (roe_f - growth) / (coe - growth)
        intrinsic_pbv = pbv_fair * bvps_f

    # ---- Blend 50/50 dengan fallback ----
    if intrinsic_ddm is not None and intrinsic_pbv is not None:
        intrinsic_value: float | None = 0.5 * intrinsic_ddm + 0.5 * intrinsic_pbv
        method = "Banking Blend (50% DDM + 50% PBV)"
        notes = "Justified PBV dan DDM dua-duanya valid."
    elif intrinsic_ddm is not None:
        intrinsic_value = intrinsic_ddm
        method = "Banking DDM only"
        notes = "Justified PBV tidak bisa dihitung (ROE <= growth atau BVPS missing)."
    elif intrinsic_pbv is not None:
        intrinsic_value = intrinsic_pbv
        method = "Banking PBV only"
        notes = "DDM tidak bisa dihitung (DPS missing/<=0 atau COE <= growth)."
    else:
        intrinsic_value = None
        method = "Banking valuation N/A"
        notes = "Data tidak cukup: butuh ROE/BVPS/DPS untuk DDM atau PBV."

    return BankingValuationResult(
        intrinsic_ddm=intrinsic_ddm,
        intrinsic_pbv=intrinsic_pbv,
        intrinsic_value=intrinsic_value,
        pbv_fair=pbv_fair,
        growth=growth,
        cost_of_equity=coe,
        payout_ratio=payout,
        dps_used=dps,
        method=method,
        notes=notes,
    )
