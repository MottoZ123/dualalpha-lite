import unittest

from research_core.schemas import compare_prediction_sets, normalize_predictions


class SchemaTests(unittest.TestCase):
    def test_normalizes_legacy_prediction(self):
        raw = {
            "600519": {
                "最新价格": 1500.5,
                "raw_prob": 0.61,
                "sector": "main",
                "档位": "A",
                "专家底牌": "XGB:60%|LGB:62%|CAT:61%|TF:59%",
                "模型权重": "XGB:25%|LGB:25%|CAT:25%|TF:25%",
            }
        }
        row = normalize_predictions(raw, "tx")[0]
        self.assertEqual(row["engine"], "TX")
        self.assertEqual(row["price"], 1500.5)
        self.assertAlmostEqual(row["component_probabilities"]["xgb"], 0.60)

    def test_comparison_is_descriptive_not_trading_instruction(self):
        tx = {"600519": {"raw_prob": 0.60}}
        bs = {"600519": {"raw_prob": 0.50}}
        result = compare_prediction_sets(tx, bs, 0.53)
        self.assertEqual(result["rows"][0]["consensus"], "tx_only")
        self.assertNotIn("action", result["rows"][0])


if __name__ == "__main__":
    unittest.main()
