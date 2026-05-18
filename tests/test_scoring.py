"""Unit tests untuk analyzer.scoring.

Run dari root project:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

from analyzer.scoring import (
    SINGLE_METHOD_HAIRCUT,
    build_scorecard,
    conservative_intrinsic_value,
    earnings_stability_label,
    margin_of_safety,
    overall_verdict,
    quality_score,
    risk_score,
    upside,
    valuation_score,
)


class TestConservativeIntrinsicValue(unittest.TestCase):
    def test_average_when_both_available(self):
        iv, method = conservative_intrinsic_value(graham=10000, dcf=14000)
        self.assertEqual(iv, 12000.0)
        self.assertIn("Blend", method)

    def test_haircut_when_only_graham(self):
        iv, method = conservative_intrinsic_value(graham=10000, dcf=None)
        self.assertAlmostEqual(iv, 10000 * (1 - SINGLE_METHOD_HAIRCUT))
        self.assertIn("Graham", method)

    def test_haircut_when_only_dcf(self):
        iv, method = conservative_intrinsic_value(graham=None, dcf=8000)
        self.assertAlmostEqual(iv, 8000 * (1 - SINGLE_METHOD_HAIRCUT))
        self.assertIn("DCF", method)

    def test_none_when_no_input(self):
        iv, method = conservative_intrinsic_value(graham=None, dcf=None)
        self.assertIsNone(iv)
        self.assertEqual(method, "N/A")

    def test_negative_or_zero_treated_as_missing(self):
        iv, method = conservative_intrinsic_value(graham=-100, dcf=0)
        self.assertIsNone(iv)


class TestMosUpside(unittest.TestCase):
    def test_mos_matches_user_example(self):
        # User example: price=9200, IV=12000 -> MOS 23%, upside 30%.
        mos = margin_of_safety(intrinsic=12000, price=9200)
        ups = upside(intrinsic=12000, price=9200)
        self.assertAlmostEqual(mos, (12000 - 9200) / 12000, places=4)
        self.assertAlmostEqual(ups, (12000 - 9200) / 9200, places=4)
        self.assertGreater(mos, 0.23)
        self.assertLess(mos, 0.24)
        self.assertGreater(ups, 0.30)
        self.assertLess(ups, 0.31)

    def test_mos_negative_when_overvalued(self):
        self.assertLess(margin_of_safety(10000, 12000), 0)

    def test_none_when_inputs_missing(self):
        self.assertIsNone(margin_of_safety(None, 1000))
        self.assertIsNone(margin_of_safety(1000, None))
        self.assertIsNone(upside(None, 100))
        self.assertIsNone(upside(100, 0))


class TestEarningsStability(unittest.TestCase):
    def test_high(self):
        self.assertEqual(earnings_stability_label(0.01), "High")

    def test_medium(self):
        self.assertEqual(earnings_stability_label(0.04), "Medium")

    def test_low(self):
        self.assertEqual(earnings_stability_label(0.10), "Low")

    def test_na(self):
        self.assertEqual(earnings_stability_label(None), "N/A")


class TestSubScores(unittest.TestCase):
    def _strong_metrics(self) -> dict:
        return {
            "roe": 0.25,
            "roa": 0.12,
            "net_margin": 0.30,
            "operating_margin": 0.40,
            "net_margin_stability_stdev": 0.01,
            "per": 9.0,
            "pbv": 1.2,
            "peg": 0.8,
            "der": 0.2,
            "current_ratio": 2.5,
            "interest_coverage": 15.0,
            "beta": 0.7,
        }

    def _weak_metrics(self) -> dict:
        return {
            "roe": 0.02,
            "roa": 0.005,
            "net_margin": 0.01,
            "operating_margin": 0.02,
            "net_margin_stability_stdev": 0.20,
            "per": 60.0,
            "pbv": 9.0,
            "peg": 8.0,
            "der": 4.0,
            "current_ratio": 0.6,
            "interest_coverage": 1.0,
            "beta": 1.8,
        }

    def test_quality_strong_vs_weak(self):
        q_strong = quality_score(self._strong_metrics())
        q_weak = quality_score(self._weak_metrics())
        self.assertIsNotNone(q_strong)
        self.assertIsNotNone(q_weak)
        self.assertGreater(q_strong, q_weak)
        self.assertGreaterEqual(q_strong, 80)
        self.assertLessEqual(q_weak, 50)

    def test_valuation_strong_vs_weak(self):
        v_strong = valuation_score(self._strong_metrics(), mos=0.30)
        v_weak = valuation_score(self._weak_metrics(), mos=-0.30)
        self.assertIsNotNone(v_strong)
        self.assertIsNotNone(v_weak)
        self.assertGreater(v_strong, v_weak)

    def test_risk_strong_vs_weak(self):
        r_strong = risk_score(self._strong_metrics())
        r_weak = risk_score(self._weak_metrics())
        self.assertIsNotNone(r_strong)
        self.assertIsNotNone(r_weak)
        self.assertGreater(r_strong, r_weak)

    def test_returns_none_when_all_inputs_missing(self):
        self.assertIsNone(quality_score({}))
        self.assertIsNone(valuation_score({}, mos=None))
        self.assertIsNone(risk_score({}))


class TestVerdict(unittest.TestCase):
    def test_buy_when_strong_and_undervalued(self):
        composite, verdict = overall_verdict(85, 80, 78, mos=0.25)
        self.assertEqual(verdict, "BUY")
        self.assertGreaterEqual(composite, 75)

    def test_accumulate_when_decent_and_small_mos(self):
        _, verdict = overall_verdict(70, 65, 65, mos=0.08)
        self.assertEqual(verdict, "ACCUMULATE")

    def test_hold_when_mediocre(self):
        _, verdict = overall_verdict(60, 55, 55, mos=0.0)
        self.assertEqual(verdict, "HOLD")

    def test_reduce_when_overvalued(self):
        _, verdict = overall_verdict(70, 60, 60, mos=-0.20)
        self.assertEqual(verdict, "REDUCE")

    def test_sell_when_extreme_overvalued(self):
        _, verdict = overall_verdict(60, 60, 60, mos=-0.40)
        self.assertEqual(verdict, "SELL")

    def test_sell_when_low_composite(self):
        _, verdict = overall_verdict(20, 20, 20, mos=0.0)
        self.assertEqual(verdict, "SELL")


class TestBuildScorecard(unittest.TestCase):
    def test_full_pipeline_user_example(self):
        # Simulate angka contoh user: Price 9200, Graham=DCF=12000.
        metrics = {
            "current_price": 9200,
            "roe": 0.22,
            "roa": 0.035,
            "net_margin": 0.35,
            "operating_margin": 0.42,
            "net_margin_stability_stdev": 0.015,
            "per": 18.0,
            "pbv": 4.5,
            "peg": 1.2,
            "der": 0.4,
            "current_ratio": 1.8,
            "interest_coverage": 12.0,
            "beta": 0.9,
        }
        sc = build_scorecard(metrics, graham_value=12000, dcf_value=12000)
        self.assertAlmostEqual(sc.intrinsic_value, 12000.0)
        self.assertEqual(sc.intrinsic_method, "Blend (Graham+DCF)")
        self.assertGreater(sc.mos, 0.23)
        self.assertLess(sc.mos, 0.24)
        self.assertEqual(sc.earnings_stability, "High")
        # Komposit cukup tinggi -> minimal HOLD/ACCUMULATE/BUY (jangan SELL/REDUCE).
        self.assertNotIn(sc.verdict, {"SELL", "REDUCE"})


if __name__ == "__main__":
    unittest.main()
