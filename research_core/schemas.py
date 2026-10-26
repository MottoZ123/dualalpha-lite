"""Stable JSON schemas over the legacy TX/BS prediction dictionaries."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


_PAIR_RE = re.compile(r"([A-Za-z]+)\s*:\s*([0-9.]+)%")


def _pairs(value: Any) -> dict[str, float]:
    if not isinstance(value, str):
        return {}
    return {name.lower(): float(number) / 100.0 for name, number in _PAIR_RE.findall(value)}


def _first(row: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return default


@dataclass(frozen=True)
class PredictionRecord:
    code: str
    engine: str
    probability: float
    price: float | None
    sector: str
    tier: str
    component_probabilities: dict[str, float]
    model_weights: dict[str, float]
    status: str


def normalize_predictions(predictions: dict, engine: str) -> list[dict]:
    records = []
    for code, raw in sorted((predictions or {}).items()):
        if not isinstance(raw, dict):
            continue
        probability = raw.get("raw_prob")
        if probability is None:
            records.append(asdict(PredictionRecord(
                code=str(code), engine=engine.upper(), probability=0.0, price=None,
                sector=str(raw.get("sector", "")), tier="", component_probabilities={},
                model_weights={}, status=str(_first(raw, ("状态", "鐘舵€?"), "invalid")),
            )))
            continue
        price = _first(raw, ("最新价格", "鏈€鏂颁环鏍?"))
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
        records.append(asdict(PredictionRecord(
            code=str(code),
            engine=engine.upper(),
            probability=max(0.0, min(float(probability), 1.0)),
            price=price,
            sector=str(raw.get("sector", "")),
            tier=str(_first(raw, ("档位", "妗ｄ綅"), "")),
            component_probabilities=_pairs(_first(raw, ("专家底牌", "涓撳搴曠墝"), "")),
            model_weights=_pairs(_first(raw, ("模型权重", "妯″瀷鏉冮噸"), "")),
            status="ok",
        )))
    return records


def compare_prediction_sets(tx: dict, bs: dict, threshold: float = 0.53) -> dict:
    tx_rows = {row["code"]: row for row in normalize_predictions(tx, "TX") if row["status"] == "ok"}
    bs_rows = {row["code"]: row for row in normalize_predictions(bs, "BS") if row["status"] == "ok"}
    rows = []
    for code in sorted(set(tx_rows) | set(bs_rows)):
        tx_prob = tx_rows.get(code, {}).get("probability")
        bs_prob = bs_rows.get(code, {}).get("probability")
        tx_positive = tx_prob is not None and tx_prob >= threshold
        bs_positive = bs_prob is not None and bs_prob >= threshold
        if tx_positive and bs_positive:
            consensus = "dual_positive"
        elif tx_positive:
            consensus = "tx_only"
        elif bs_positive:
            consensus = "bs_only"
        else:
            consensus = "dual_below_threshold"
        rows.append({
            "code": code,
            "tx_probability": tx_prob,
            "bs_probability": bs_prob,
            "spread": round(tx_prob - bs_prob, 6) if tx_prob is not None and bs_prob is not None else None,
            "consensus": consensus,
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "count": len(rows),
        "rows": rows,
    }
