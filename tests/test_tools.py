import json
import tempfile
import unittest
from pathlib import Path

from research_core.config import AppConfig
from research_core.tools import latest_comparison, latest_predictions


class ToolTests(unittest.TestCase):
    def config(self, reports: Path) -> AppConfig:
        return AppConfig(
            data_dir=reports.parent,
            reports_dir=reports,
            vibe_base_url="http://127.0.0.1:8900",
            vibe_api_key="",
            vibe_timeout_seconds=1,
            api_key="",
            allow_origins=("http://127.0.0.1",),
            consensus_threshold=0.53,
            enable_model_execution=False,
        )

    def test_reads_latest_complete_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp) / "reports"
            day = reports / "20260714"
            day.mkdir(parents=True)
            (day / "tx_raw_preds.json").write_text(json.dumps({"600519": {"raw_prob": 0.6}}), encoding="utf-8")
            (day / "bs_raw_preds.json").write_text(json.dumps({"600519": {"raw_prob": 0.55}}), encoding="utf-8")
            incomplete = reports / "20260715"
            incomplete.mkdir()
            (incomplete / "1_TX_Full_Report.md").write_text("partial", encoding="utf-8")
            cfg = self.config(reports)
            self.assertEqual(latest_predictions("tx", config=cfg)["day"], "20260714")
            self.assertEqual(latest_comparison(config=cfg)["rows"][0]["consensus"], "dual_positive")


if __name__ == "__main__":
    unittest.main()
