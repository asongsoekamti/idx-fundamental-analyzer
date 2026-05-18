"""Unit tests untuk analyzer.banking + integrasi dengan ScoreCard.

Run dari root project:

    python -m unittest tests.test_banking -v
"""

from __future__ import annotations

import unittest

from analyzer.banking import (
    DEFAULT_COST_OF_EQUITY,
    DEFAULT_PAYOUT_RATIO,
    GROWTH_CAP,
    ROE_DOWNGRADE_THRESHOLD,
    banking_valuation,
    is_banking_stock,
)
from analyzer.scoring import apply_quality_floor, build_scorecard


# ----------------------------- Detector -----------------------------

class TestIsBankingStock(unittest.TestCase):
    def test_yfinance_banks_regional(self):
        # Persis seperti label yfinance untuk BBCA / BBRI / BBNI.
        m = {"sector": "Financial Services", "industry": "Banks - Regional"}
        self.assertTrue(is_banking_stock(m))

    def test_yfinance_banks_diversified(self):
        m = {"sector": "Financial Services", "industry": "Banks - Diversified"}
        self.assertTrue(is_banking_stock(m))

    def test_case_insensitive(self):
        m = {"sector": "FINANCIAL SERVICES", "industry": "BANKS"}
        self.assertTrue(is_banking_stock(m))

    def test_non_bank_financial_services(self):
        # Insurance/asset manager/securities -> bukan bank.
        m = {"sector": "Financial Services", "industry": "Insurance - Diversified"}
        self.assertFalse(is_banking_stock(m))

    def test_telekomunikasi_bukan_bank(self):
        m = {"sector": "Communication Services", "industry": "Telecom Services"}
        self.assertFalse(is_banking_stock(m))

    def test_consumer_goods_bukan_bank(self):
        m = {"sector": "Consumer Defensive", "industry": "Tobacco"}
        self.assertFalse(is_banking_stock(m))

    def test_empty_metrics(self):
        self.assertFalse(is_banking_stock({}))
        self.assertFalse(is_banking_stock({"sector": None, "industry": None}))


# ----------------------------- Banking valuation -----------------------------

class TestBankingValuation(unittest.TestCase):
    def _bbca_like_metrics(self) -> dict:
        # Profil mirip BBCA: ROE 18%, payout 60% (realistis), BVPS solid, DPS jelas.
        # Dipilih supaya growth = 0.18*0.40 = 0.072 < COE default 0.10 (r > g).
        return {
            "sector": "Financial Services",
            "industry": "Banks - Regional",
            "current_price": 9200.0,
            "roe": 0.18,
            "payout_ratio": 0.60,
            "book_value_per_share": 2400.0,
            "eps": 510.0,
            "dividend_rate": 300.0,  # IDR per share per year
        }

    def test_full_blend_valid(self):
        m = self._bbca_like_metrics()
        bv = banking_valuation(m)
        # Semua komponen harus terhitung
        self.assertIsNotNone(bv.intrinsic_ddm)
        self.assertIsNotNone(bv.intrinsic_pbv)
        self.assertIsNotNone(bv.intrinsic_value)
        self.assertEqual(bv.method, "Banking Blend (50% DDM + 50% PBV)")
        # Final IV = rata-rata DDM + PBV (50/50)
        self.assertAlmostEqual(
            bv.intrinsic_value,
            0.5 * bv.intrinsic_ddm + 0.5 * bv.intrinsic_pbv,
            places=4,
        )

    def test_growth_cap_applied(self):
        # ROE 30%, payout 0% -> raw growth 30%, harus di-cap ke 10%.
        m = {"roe": 0.30, "payout_ratio": 0.0, "book_value_per_share": 1000,
             "eps": 300, "dividend_rate": 0.0}
        bv = banking_valuation(m)
        self.assertAlmostEqual(bv.growth, GROWTH_CAP)

    def test_growth_uses_min_with_cap(self):
        # ROE 14%, payout 50% -> raw 7%, di bawah cap.
        m = {"roe": 0.14, "payout_ratio": 0.50, "book_value_per_share": 1000,
             "eps": 200, "dividend_rate": 100}
        bv = banking_valuation(m)
        self.assertAlmostEqual(bv.growth, 0.14 * 0.5, places=4)
        self.assertLess(bv.growth, GROWTH_CAP)

    def test_default_payout_when_missing(self):
        m = {"roe": 0.15, "payout_ratio": None, "book_value_per_share": 1000,
             "eps": 200, "dividend_rate": 80}
        bv = banking_valuation(m)
        self.assertAlmostEqual(bv.payout_ratio, DEFAULT_PAYOUT_RATIO)

    def test_default_coe_when_not_passed(self):
        m = self._bbca_like_metrics()
        bv = banking_valuation(m)
        self.assertAlmostEqual(bv.cost_of_equity, DEFAULT_COST_OF_EQUITY)

    def test_custom_coe_override(self):
        m = self._bbca_like_metrics()
        bv = banking_valuation(m, cost_of_equity=0.13)
        self.assertAlmostEqual(bv.cost_of_equity, 0.13)
        # COE lebih tinggi -> IV lebih rendah (denominator lebih besar).
        bv_default = banking_valuation(m)
        self.assertLess(bv.intrinsic_value, bv_default.intrinsic_value)

    def test_dps_fallback_from_eps_payout(self):
        # ROE 0.12 + payout 0.40 -> growth = 0.072, di bawah COE 0.10.
        m = {"roe": 0.12, "payout_ratio": 0.40, "book_value_per_share": 1000,
             "eps": 250, "dividend_rate": None}
        bv = banking_valuation(m)
        # DPS yang dipakai harus = EPS * payout
        self.assertAlmostEqual(bv.dps_used, 250 * 0.40)
        self.assertIsNotNone(bv.intrinsic_ddm)

    def test_pbv_fair_formula(self):
        # ROE=0.20, COE=0.10, growth=min(0.20*0.5, 0.10)=0.10 -> r==g, formula
        # tidak terdefinisi (Gordon r>g). Harus None.
        m = {"roe": 0.20, "payout_ratio": 0.50, "book_value_per_share": 1000,
             "eps": 200, "dividend_rate": 100}
        bv = banking_valuation(m, cost_of_equity=0.10)
        # growth akan dihitung sebagai min(0.10, 0.10)=0.10 == COE.
        self.assertEqual(bv.growth, 0.10)
        self.assertIsNone(bv.intrinsic_ddm)
        self.assertIsNone(bv.intrinsic_pbv)
        self.assertIsNone(bv.intrinsic_value)

    def test_ddm_only_when_pbv_unavailable(self):
        # BVPS missing -> PBV None, tapi DDM masih bisa.
        # ROE 0.12 + payout 0.40 supaya growth = 0.072 < COE 0.10.
        m = {"roe": 0.12, "payout_ratio": 0.40, "book_value_per_share": None,
             "eps": 200, "dividend_rate": 80}
        bv = banking_valuation(m)
        self.assertIsNotNone(bv.intrinsic_ddm)
        self.assertIsNone(bv.intrinsic_pbv)
        self.assertEqual(bv.intrinsic_value, bv.intrinsic_ddm)
        self.assertEqual(bv.method, "Banking DDM only")

    def test_pbv_only_when_ddm_unavailable(self):
        # DPS missing dan EPS<=0 -> DDM None. ROE 0.12 supaya PBV valid.
        m = {"roe": 0.12, "payout_ratio": 0.40, "book_value_per_share": 1000,
             "eps": -50, "dividend_rate": 0}
        bv = banking_valuation(m)
        self.assertIsNone(bv.intrinsic_ddm)
        self.assertIsNotNone(bv.intrinsic_pbv)
        self.assertEqual(bv.intrinsic_value, bv.intrinsic_pbv)

    def test_all_missing_returns_none(self):
        bv = banking_valuation({})
        self.assertIsNone(bv.intrinsic_ddm)
        self.assertIsNone(bv.intrinsic_pbv)
        self.assertIsNone(bv.intrinsic_value)
        self.assertIn("Insufficient", bv.notes + bv.method)

    def test_payout_clamped_to_range(self):
        # Payout > 1 (yfinance bug) harus di-clamp ke 1.
        m = {"roe": 0.18, "payout_ratio": 1.5, "book_value_per_share": 1000,
             "eps": 200, "dividend_rate": 80}
        bv = banking_valuation(m)
        self.assertEqual(bv.payout_ratio, 1.0)


# ----------------------------- Quality floor -----------------------------

class TestQualityFloor(unittest.TestCase):
    def test_buy_downgraded_when_low_roe(self):
        new_verdict, applied = apply_quality_floor("BUY", roe=0.08)
        self.assertEqual(new_verdict, "HOLD")
        self.assertTrue(applied)

    def test_accumulate_downgraded_when_low_roe(self):
        new_verdict, applied = apply_quality_floor("ACCUMULATE", roe=0.05)
        self.assertEqual(new_verdict, "HOLD")
        self.assertTrue(applied)

    def test_buy_kept_when_roe_at_threshold(self):
        # ROE persis 12% -> tidak downgrade.
        new_verdict, applied = apply_quality_floor("BUY", roe=ROE_DOWNGRADE_THRESHOLD)
        self.assertEqual(new_verdict, "BUY")
        self.assertFalse(applied)

    def test_buy_kept_when_high_roe(self):
        new_verdict, applied = apply_quality_floor("BUY", roe=0.25)
        self.assertEqual(new_verdict, "BUY")
        self.assertFalse(applied)

    def test_hold_not_changed(self):
        new_verdict, applied = apply_quality_floor("HOLD", roe=0.05)
        self.assertEqual(new_verdict, "HOLD")
        self.assertFalse(applied)

    def test_sell_not_promoted(self):
        # ROE bagus tetap SELL kalau memang SELL.
        new_verdict, applied = apply_quality_floor("SELL", roe=0.30)
        self.assertEqual(new_verdict, "SELL")
        self.assertFalse(applied)

    def test_none_roe_no_change(self):
        new_verdict, applied = apply_quality_floor("BUY", roe=None)
        self.assertEqual(new_verdict, "BUY")
        self.assertFalse(applied)


# ----------------------------- ScoreCard integration -----------------------------

class TestBuildScorecardBanking(unittest.TestCase):
    def _bank_metrics(self, **overrides) -> dict:
        # Profil dipilih supaya growth (0.072) < COE default (0.10),
        # sehingga formula Gordon DDM & Justified PBV terdefinisi.
        m = {
            "ticker": "BBCA.JK",
            "name": "Bank Central Asia Tbk",
            "sector": "Financial Services",
            "industry": "Banks - Regional",
            "currency": "IDR",
            "current_price": 9200.0,
            "roe": 0.18,
            "roa": 0.035,
            "net_margin": 0.40,
            "operating_margin": 0.45,
            "net_margin_stability_stdev": 0.012,
            "per": 22.0,
            "pbv": 5.0,
            "peg": 1.5,
            "der": 0.50,
            "current_ratio": 1.2,
            "interest_coverage": 5.0,
            "beta": 0.85,
            "payout_ratio": 0.60,
            "book_value_per_share": 2400.0,
            "eps": 510.0,
            "dividend_rate": 300.0,
        }
        m.update(overrides)
        return m

    def test_banking_branch_used(self):
        m = self._bank_metrics()
        sc = build_scorecard(m, graham_value=99999, dcf_value=99999)
        # graham/dcf 99999 harus DIABAIKAN karena banking.
        self.assertTrue(sc.is_banking)
        self.assertIsNotNone(sc.intrinsic_ddm)
        self.assertIsNotNone(sc.intrinsic_pbv)
        self.assertIsNotNone(sc.intrinsic_value)
        self.assertNotEqual(sc.intrinsic_value, 99999)
        self.assertIn("DDM", sc.intrinsic_method + " ".join(sc.notes))

    def test_non_bank_uses_graham_dcf(self):
        m = self._bank_metrics(
            sector="Consumer Defensive",
            industry="Tobacco",
        )
        sc = build_scorecard(m, graham_value=10000, dcf_value=14000)
        self.assertFalse(sc.is_banking)
        self.assertIsNone(sc.intrinsic_ddm)
        self.assertIsNone(sc.intrinsic_pbv)
        # Blend Graham+DCF average = 12000
        self.assertAlmostEqual(sc.intrinsic_value, 12000.0)

    def test_required_outputs_present(self):
        # Spec user requirement #8: output harus include intrinsic_ddm,
        # intrinsic_pbv, final intrinsic_value, MOS, verdict.
        m = self._bank_metrics()
        sc = build_scorecard(m, None, None)
        self.assertIsNotNone(sc.intrinsic_ddm)
        self.assertIsNotNone(sc.intrinsic_pbv)
        self.assertIsNotNone(sc.intrinsic_value)
        self.assertIsNotNone(sc.mos)
        self.assertIn(sc.verdict, {"BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL"})

    def test_quality_floor_applied_on_low_roe_bank(self):
        # ROE 8% -> regardless of MOS, BUY harus jadi HOLD.
        m = self._bank_metrics(roe=0.08, current_price=1.0)  # MOS ~100%
        sc = build_scorecard(m, None, None)
        self.assertTrue(sc.is_banking)
        # MOS ekstrim positif tapi verdict tetap HOLD karena ROE rendah.
        self.assertGreater(sc.mos, 0.5)
        self.assertEqual(sc.verdict, "HOLD")
        self.assertTrue(sc.quality_floor_applied)

    def test_high_roe_bank_can_be_buy(self):
        # ROE bagus + harga di bawah IV -> BUY/ACCUMULATE.
        m = self._bank_metrics(roe=0.22, current_price=5000.0)
        sc = build_scorecard(m, None, None)
        self.assertTrue(sc.is_banking)
        self.assertFalse(sc.quality_floor_applied)
        self.assertIn(sc.verdict, {"BUY", "ACCUMULATE"})

    def test_mos_formula_matches_user_spec(self):
        # MOS = (IV - price) / IV.
        m = self._bank_metrics()
        sc = build_scorecard(m, None, None)
        expected = (sc.intrinsic_value - m["current_price"]) / sc.intrinsic_value
        self.assertAlmostEqual(sc.mos, expected, places=6)


if __name__ == "__main__":
    unittest.main()
