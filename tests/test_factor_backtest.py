import unittest

import numpy as np
import pandas as pd

from quant.factor_backtest import _safe_factor_formula, compute_factor_frame, evaluate_factor_panel, evaluate_factor_relationships, local_dual_track_walk_forward, walk_forward_t1_backtest


class FactorBacktestTests(unittest.TestCase):
    def test_custom_factor_formula_uses_safe_arithmetic_only(self):
        frame = pd.DataFrame({"Return_20": [1.0, 2.0], "ATR_Ratio_14_60": [2.0, 4.0]})
        self.assertEqual(_safe_factor_formula(frame, "Return_20 / ATR_Ratio_14_60").tolist(), [.5, .5])
        with self.assertRaises(ValueError):
            _safe_factor_formula(frame, "__import__('os').system('echo unsafe')")

    def test_metrics_are_derived_from_historical_panel(self):
        rng = np.random.default_rng(42)
        dates = pd.date_range("2023-01-02", periods=180, freq="B")
        frames = []
        for index, code in enumerate(("000001", "000002", "000003", "000004", "000005")):
            returns = rng.normal(0.0003 + index * 0.0002, 0.008, len(dates))
            close = 100 * np.cumprod(1 + returns)
            frames.append(pd.DataFrame({
                "date": dates,
                "code": code,
                "Close": close,
                "Return_5": pd.Series(close).pct_change(5).to_numpy(),
                "Return_20": pd.Series(close).pct_change(20).to_numpy(),
                "Z_Score_20": (pd.Series(close) - pd.Series(close).rolling(20).mean()).div(pd.Series(close).rolling(20).std()).to_numpy(),
            }))
        metrics = evaluate_factor_panel(pd.concat(frames, ignore_index=True), ["Return_5", "Return_20", "Z_Score_20"], label_horizon=5)
        self.assertEqual(set(metrics), {"Return_5", "Return_20", "Z_Score_20"})
        for result in metrics.values():
            self.assertIn("rankIc", result)
            self.assertIn("maxDrawdown", result)
            self.assertIn("turnover", result)
            self.assertEqual(result["leakage"], "passed")
            self.assertTrue(result["period"].startswith("2023-"))

        relationships = evaluate_factor_relationships(
            pd.concat(frames, ignore_index=True),
            ["Return_5", "Return_20", "Z_Score_20"],
            {"Return_5": 0.4, "Return_20": 0.35, "Z_Score_20": 0.25},
            label_horizon=5,
        )
        self.assertEqual(set(relationships["correlation"]), {"Return_5", "Return_20", "Z_Score_20"})
        self.assertIn("compositeRankIc", relationships)
        self.assertEqual(set(relationships["marginalContribution"]), {"Return_5", "Return_20", "Z_Score_20"})

        walk_forward = walk_forward_t1_backtest(
            pd.concat(frames, ignore_index=True), ["Return_5", "Return_20", "Z_Score_20"],
            {"minTrainDays": 80, "testWindowDays": 20, "feeBps": 8, "slippageBps": 5},
        )
        self.assertEqual(walk_forward["horizon"], "T+1")
        self.assertEqual(walk_forward["leakageCheck"], "passed-by-date-boundary")
        self.assertGreater(walk_forward["outOfSampleDays"], 0)
        self.assertLessEqual(walk_forward["averageTurnover"], 1.0)
        for fold in walk_forward["folds"]:
            self.assertLess(fold["trainEnd"], fold["testStart"])

    def test_local_tx_bs_dual_horizon_separates_attention_and_return_objectives(self):
        rng = np.random.default_rng(7)
        dates = pd.date_range("2022-01-03", periods=330, freq="B")
        market_returns = pd.Series(rng.normal(.0002, .006, len(dates)), index=dates)
        frames = []
        codes = ("300308", "300502", "688008", "301297", "600522", "002335", "601899")
        for index, code in enumerate(codes):
            returns = .35 * market_returns.to_numpy() + rng.normal(.0001 + index * .00003, .009, len(dates))
            close = 50 * np.cumprod(1 + returns)
            raw = pd.DataFrame({
                "date": dates, "open": close * (1 + rng.normal(0, .002, len(dates))),
                "high": close * 1.012, "low": close * .988, "close": close,
                "volume": rng.integers(1_000_000, 8_000_000, len(dates)),
                "amount": rng.integers(50_000_000, 400_000_000, len(dates)),
                "turn": rng.uniform(.3, 4.0, len(dates)), "pct_chg": returns,
            })
            frame = compute_factor_frame(raw, market_returns).reset_index()
            frame["code"] = code
            frames.append(frame)
        panel = pd.concat(frames, ignore_index=True)
        panel["Turn"] = np.nan  # Tencent history can omit turnover; BS must degrade explicitly, not disappear.
        t1 = local_dual_track_walk_forward(panel, 1, {"minTrainDays": 140, "testWindowDays": 30})
        t5 = local_dual_track_walk_forward(panel, 5, {"minTrainDays": 140, "testWindowDays": 30, "t5ObservationStep": 5})
        self.assertEqual(t1["primaryObjective"], "attention-hit-rate")
        self.assertEqual(t1["tradeAssumption"], "no-daily-trade-assumption")
        self.assertEqual(t5["primaryObjective"], "non-overlapping-cost-adjusted-return")
        self.assertTrue(t5["tracks"]["tx"]["returnStudy"]["nonOverlapping"])
        self.assertGreater(t1["tracks"]["bs"]["signals"], 0)
        self.assertTrue(any("Turn" in model["omittedFactors"] for fold in t1["folds"] for model in fold["models"] if model["track"] == "bs" and model["sector"] == "tech"))
        for result in (t1, t5):
            self.assertEqual(result["leakageCheck"], "passed-label-known-before-test")
            for fold in result["folds"]:
                self.assertLess(fold["labelKnownThrough"], fold["testStart"])


if __name__ == "__main__":
    unittest.main()
