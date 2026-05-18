"""Unit tests untuk analyzer.report (formatter teks/tabel)."""

from __future__ import annotations

import unittest

from analyzer.report import (
    DcfAssumptions,
    SUMMARY_HEADERS,
    build_detail_rows,
    build_summary_rows,
    fmt_money,
    fmt_money_short,
    fmt_num,
    fmt_pct,
    render_ascii_table,
    render_stock_section,
    verdict_marker,
)
from analyzer.scoring import build_scorecard


class TestFormatters(unittest.TestCase):
    def test_fmt_pct(self):
        self.assertEqual(fmt_pct(0.235), "23.50%")
        self.assertEqual(fmt_pct(None), "N/A")
        self.assertEqual(fmt_pct(float("nan")), "N/A")

    def test_fmt_num(self):
        self.assertEqual(fmt_num(1234.5), "1,234.50")
        self.assertEqual(fmt_num(1234.5, decimals=0), "1,234")
        self.assertEqual(fmt_num(15.0, suffix="x"), "15.00x")
        self.assertEqual(fmt_num(None), "N/A")

    def test_fmt_money(self):
        self.assertEqual(fmt_money(9200), "IDR 9,200")
        self.assertEqual(fmt_money(9200, currency="USD"), "USD 9,200")
        self.assertEqual(fmt_money(None), "N/A")

    def test_fmt_money_short(self):
        self.assertIn("T", fmt_money_short(2.5e12))
        self.assertIn("M", fmt_money_short(2.5e9))
        self.assertEqual(fmt_money_short(None), "N/A")


class TestVerdictMarker(unittest.TestCase):
    def test_known_verdicts(self):
        self.assertIn("BUY", verdict_marker("BUY"))
        self.assertIn("[+]", verdict_marker("BUY"))
        self.assertIn("[-]", verdict_marker("SELL"))
        self.assertIn("[=]", verdict_marker("HOLD"))


class TestAsciiTable(unittest.TestCase):
    def test_render_basic(self):
        headers = ["A", "B", "C"]
        rows = [["1", "22", "333"], ["44", "5", "6"]]
        out = render_ascii_table(headers, rows)
        self.assertIn("A", out)
        self.assertIn("333", out)
        # Border kanan dan kiri
        for line in out.splitlines():
            self.assertTrue(line.startswith("+") or line.startswith("|"))

    def test_render_handles_empty_rows(self):
        out = render_ascii_table(["X", "Y"], [])
        # Tidak crash, minimal punya header line
        self.assertIn("X", out)


class TestDetailRows(unittest.TestCase):
    def test_groups_present(self):
        metrics = _example_metrics()
        sc = build_scorecard(metrics, graham_value=12000, dcf_value=12000)
        rows = build_detail_rows(metrics, sc, DcfAssumptions())
        groups = {r[0] for r in rows}
        for required in {"Identity", "Valuation", "Profitability", "Growth",
                         "Financial Health", "Risk", "DCF Assumptions", "Score"}:
            self.assertIn(required, groups)

    def test_summary_rows_match_headers(self):
        metrics = _example_metrics()
        sc = build_scorecard(metrics, graham_value=12000, dcf_value=12000)
        rows = build_summary_rows([(metrics, sc)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), len(SUMMARY_HEADERS))


class TestStockSection(unittest.TestCase):
    def test_renders_user_facing_layout(self):
        metrics = _example_metrics()
        sc = build_scorecard(metrics, graham_value=12000, dcf_value=12000)
        out = render_stock_section(metrics, sc, DcfAssumptions())

        # Layout sections seperti di contoh user
        self.assertIn("Ticker:", out)
        self.assertIn("Price", out)
        self.assertIn("Intrinsic Value", out)
        self.assertIn("MOS", out)
        self.assertIn("Upside", out)
        self.assertIn("--- Profitability ---", out)
        self.assertIn("--- Growth ---", out)
        self.assertIn("--- Valuation ---", out)
        self.assertIn("--- Financial Health ---", out)
        self.assertIn("--- Risk ---", out)
        self.assertIn("--- DCF Assumptions ---", out)
        self.assertIn("--- Score ---", out)
        self.assertIn("Overall", out)


def _example_metrics() -> dict:
    return {
        "ticker": "BBCA.JK",
        "name": "Bank Central Asia",
        "sector": "Financial Services",
        "industry": "Banks - Regional",
        "currency": "IDR",
        "current_price": 9200,
        "market_cap": 1.13e15,
        "free_cash_flow": 7.5e13,
        "shares_outstanding": 1.23e11,
        "eps": 510,
        "book_value_per_share": 2400,
        "roe": 0.22,
        "roa": 0.035,
        "net_margin": 0.35,
        "operating_margin": 0.42,
        "revenue_growth_yoy": 0.08,
        "earnings_growth_yoy": 0.10,
        "revenue_cagr_5y": 0.09,
        "per": 18.0,
        "pbv": 4.5,
        "peg": 1.2,
        "der": 0.4,
        "current_ratio": 1.8,
        "interest_coverage": 12.0,
        "beta": 0.9,
        "net_margin_stability_stdev": 0.015,
    }


if __name__ == "__main__":
    unittest.main()
