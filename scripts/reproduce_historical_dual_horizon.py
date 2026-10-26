"""Reproducible current-universe TX/BS T+1 attention + T+5 return study."""

from __future__ import annotations

import json
from pathlib import Path

from factor_backtest import run_factor_backtest
from workbench_core.config import ORIGINAL_UNIVERSE, ROOT


if __name__ == "__main__":
    output = ROOT / "output" / "backtests" / "motto-local-tx-bs-dual-horizon-20260817-v2"
    result = run_factor_backtest(
        [item.code for item in ORIGINAL_UNIVERSE],
        ["Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60"],
        {
            "dateFrom": "2021-01-01", "dateTo": "2026-08-17",
            "factorPreset": "local_tx_bs", "runDualHorizon": True, "walkForward": False,
            "labelHorizon": 5, "feeBps": 8, "slippageBps": 5,
            "minTrainDays": 250, "testWindowDays": 20,
            "attentionTopN": 2, "probabilityFloor": 0.53, "t5ObservationStep": 5,
        },
        output,
    )
    compact = {}
    for horizon, package in result["dualHorizonResults"].items():
        rows = {**package.get("tracks", {}), "consensus": package.get("consensus", {})}
        compact[horizon] = {track: {"signals": values.get("signals"), "outperformanceHitRate": values.get("outperformanceHitRate"), "positiveHitRate": values.get("positiveHitRate"), "returnStudy": values.get("returnStudy")} for track, values in rows.items()}
    print(json.dumps({"outputDir": result["outputDir"], "observations": result["observations"], "summary": compact}, ensure_ascii=False, indent=2))
