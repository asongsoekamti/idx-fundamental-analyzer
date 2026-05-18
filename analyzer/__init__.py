"""IDX Fundamental Analyzer - analisis fundamental saham Indonesia."""

from analyzer.banking import (
    BankingValuationResult,
    DEFAULT_COST_OF_EQUITY,
    DEFAULT_PAYOUT_RATIO,
    GROWTH_CAP,
    ROE_DOWNGRADE_THRESHOLD,
    banking_valuation,
    is_banking_stock,
)
from analyzer.fetcher import StockFetcher
from analyzer.metrics import compute_metrics
from analyzer.valuation import (
    graham_number,
    margin_of_safety,
    simple_dcf,
    intrinsic_value_summary,
)
from analyzer.screener import screen_watchlist
from analyzer.scoring import (
    ScoreCard,
    apply_quality_floor,
    build_scorecard,
    conservative_intrinsic_value,
    earnings_stability_label,
    overall_verdict,
    quality_score,
    risk_score,
    valuation_score,
)
from analyzer.report import (
    DcfAssumptions,
    build_summary_rows,
    build_detail_rows,
    render_ascii_table,
    render_stock_section,
)

__all__ = [
    "StockFetcher",
    "compute_metrics",
    "graham_number",
    "margin_of_safety",
    "simple_dcf",
    "intrinsic_value_summary",
    "screen_watchlist",
    "ScoreCard",
    "apply_quality_floor",
    "build_scorecard",
    "conservative_intrinsic_value",
    "earnings_stability_label",
    "overall_verdict",
    "quality_score",
    "risk_score",
    "valuation_score",
    "BankingValuationResult",
    "banking_valuation",
    "is_banking_stock",
    "DEFAULT_COST_OF_EQUITY",
    "DEFAULT_PAYOUT_RATIO",
    "GROWTH_CAP",
    "ROE_DOWNGRADE_THRESHOLD",
    "DcfAssumptions",
    "build_summary_rows",
    "build_detail_rows",
    "render_ascii_table",
    "render_stock_section",
]

__version__ = "0.3.0"
