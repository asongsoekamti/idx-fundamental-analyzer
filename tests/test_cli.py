"""Test CLI: parsing args, watchlist loader (cap 50), export filenames.

Tidak melakukan network call. Network-heavy path (fetch yfinance) di-mock.
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analyze import build_parser, load_tickers
from analyzer.report import DcfAssumptions, build_summary_rows
from analyzer.scoring import build_scorecard


class TestArgparse(unittest.TestCase):
    def test_default_export_is_none(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.export, "none")
        self.assertEqual(args.wacc, 12.0)
        self.assertEqual(args.growth, 8.0)
        self.assertEqual(args.terminal, 4.0)
        self.assertEqual(args.coe, 10.0)

    def test_coe_arg_override(self):
        args = build_parser().parse_args(["--coe", "13"])
        self.assertEqual(args.coe, 13.0)

    def test_emiten_arg(self):
        args = build_parser().parse_args(["--emiten", "BBRI.JK"])
        self.assertEqual(args.emiten, "BBRI.JK")

    def test_invalid_export_choice_rejected(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--export", "html"])


class TestLoadTickers(unittest.TestCase):
    def test_emiten_takes_precedence(self):
        args = build_parser().parse_args(["--emiten", "BBCA,BBRI.JK"])
        tickers = load_tickers(args)
        self.assertEqual(tickers, ["BBCA.JK", "BBRI.JK"])

    def test_emiten_normalizes_suffix(self):
        args = build_parser().parse_args(["--emiten", "BBRI"])
        self.assertEqual(load_tickers(args), ["BBRI.JK"])

    def test_watchlist_csv_with_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wl.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ticker", "name"])
                w.writerow(["BBCA.JK", "BCA"])
                w.writerow(["BBRI.JK", "BRI"])
            args = build_parser().parse_args(["--watchlist", str(path)])
            self.assertEqual(load_tickers(args), ["BBCA.JK", "BBRI.JK"])

    def test_watchlist_caps_at_50(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ticker"])
                for i in range(80):
                    w.writerow([f"AAA{i:02d}.JK"])
            args = build_parser().parse_args(["--watchlist", str(path)])
            tickers = load_tickers(args)
            self.assertEqual(len(tickers), 50)
            self.assertEqual(tickers[0], "AAA00.JK")
            self.assertEqual(tickers[-1], "AAA49.JK")

    def test_watchlist_respects_lower_limit_arg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wl.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ticker"])
                for i in range(20):
                    w.writerow([f"BBB{i:02d}.JK"])
            args = build_parser().parse_args(["--watchlist", str(path), "--limit", "5"])
            tickers = load_tickers(args)
            self.assertEqual(len(tickers), 5)

    def test_missing_watchlist_raises(self):
        args = build_parser().parse_args(["--watchlist", "/nope/nonexistent.csv"])
        with self.assertRaises(SystemExit):
            load_tickers(args)

    def test_plain_text_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wl.txt"
            path.write_text("# komentar\nBBCA.JK\nBBRI.JK\n\n#TLKM (skipped)\n", encoding="utf-8")
            args = build_parser().parse_args(["--watchlist", str(path)])
            self.assertEqual(load_tickers(args), ["BBCA.JK", "BBRI.JK"])


class TestExportTxtRoundtrip(unittest.TestCase):
    def test_export_txt_produces_summary_and_detail(self):
        from analyzer.export import export_txt

        metrics = {
            "ticker": "BBCA.JK",
            "name": "Bank Central Asia",
            "sector": "Financial Services",
            "industry": "Banks",
            "currency": "IDR",
            "current_price": 9200,
            "free_cash_flow": 7.5e13,
            "shares_outstanding": 1.23e11,
            "market_cap": 1.13e15,
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
        sc = build_scorecard(metrics, graham_value=12000, dcf_value=12000)

        with tempfile.TemporaryDirectory() as tmp:
            out = export_txt([(metrics, sc)], DcfAssumptions(), Path(tmp) / "report.txt")
            self.assertTrue(out.exists())
            text = out.read_text(encoding="utf-8")
            # Summary table + detail section harus ada.
            self.assertIn("RINGKASAN", text)
            self.assertIn("DETAIL PER EMITEN", text)
            self.assertIn("BBCA.JK", text)
            self.assertIn("MOS", text)
            self.assertIn("DISCLAIMER", text)


if __name__ == "__main__":
    unittest.main()
