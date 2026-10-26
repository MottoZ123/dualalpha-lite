from __future__ import annotations

import math
from statistics import fmean


def _clean(values):
    result = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not result:
        raise ValueError("no finite values")
    return result


def sma(values, period: int) -> float | None:
    clean = _clean(values)
    return fmean(clean[-period:]) if len(clean) >= period else None


def moving_average_series(values, period: int) -> list[float | None]:
    normalized = [float(value) if value is not None and math.isfinite(float(value)) else None for value in values]
    result: list[float | None] = []
    for index in range(len(normalized)):
        window = normalized[max(0, index - period + 1):index + 1]
        result.append(round(fmean(window), 6) if len(window) == period and all(value is not None for value in window) else None)
    return result


def ema_series(values, period: int) -> list[float]:
    clean = _clean(values)
    alpha = 2 / (period + 1)
    result = [clean[0]]
    for value in clean[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def macd(values) -> dict:
    clean = _clean(values)
    fast, slow = ema_series(clean, 12), ema_series(clean, 26)
    dif = [a - b for a, b in zip(fast, slow)]
    dea = ema_series(dif, 9)
    histogram = [(a - b) * 2 for a, b in zip(dif, dea)]
    state = "golden" if len(dif) >= 2 and dif[-2] <= dea[-2] and dif[-1] > dea[-1] else "dead" if len(dif) >= 2 and dif[-2] >= dea[-2] and dif[-1] < dea[-1] else "above" if dif[-1] >= dea[-1] else "below"
    return {"dif": [round(x, 6) for x in dif], "dea": [round(x, 6) for x in dea], "histogram": [round(x, 6) for x in histogram], "state": state}


def rsi(values, period: int = 14) -> float | None:
    clean = _clean(values)
    if len(clean) <= period:
        return None
    changes = [b - a for a, b in zip(clean[-period - 1:-1], clean[-period:])]
    gains = fmean(max(change, 0) for change in changes)
    losses = fmean(max(-change, 0) for change in changes)
    return 100.0 if losses == 0 else round(100 - 100 / (1 + gains / losses), 4)


def condition_matrix(closes, volumes=None) -> dict:
    clean = _clean(closes)
    latest = clean[-1]
    ma20, ma60 = sma(clean, 20), sma(clean, 60)
    ma60_previous = sma(clean[:-1], 60) if len(clean) > 60 else None
    current_rsi = rsi(clean)
    momentum = macd(clean)
    volume_state = "insufficient"
    if volumes:
        volume_clean = _clean(volumes)
        if len(volume_clean) >= 20:
            volume_state = "contracting" if volume_clean[-1] < fmean(volume_clean[-20:]) else "expanding"
    conditions = [ma60 is not None and latest > ma60, ma60 is not None and ma60_previous is not None and ma60 > ma60_previous, current_rsi is not None and 35 <= current_rsi <= 70, momentum["state"] in {"golden", "above"}]
    met = sum(bool(value) for value in conditions)
    verdict = "数据不足" if len(clean) < 60 else "条件全部成立" if met == 4 else "部分成立" if met >= 2 else "条件未成立"
    m60_bias = (latest / ma60 - 1) * 100 if ma60 else None
    ma20_bias = (latest / ma20 - 1) * 100 if ma20 else None
    m60_slope = (ma60 / ma60_previous - 1) * 100 if ma60 and ma60_previous else None
    macd_strength = momentum["histogram"][-1] / latest * 100 if latest else None
    feature_profile = [
        {"key": "m60Position", "name": "M60位置", "score": round(max(0, min(100, 50 + (m60_bias or 0) * 5)), 2) if m60_bias is not None else None, "display": f"{m60_bias:+.2f}%" if m60_bias is not None else "数据不足", "state": "above" if m60_bias is not None and m60_bias > 0 else "below" if m60_bias is not None else "insufficient"},
        {"key": "m60Direction", "name": "M60方向", "score": round(max(0, min(100, 50 + (m60_slope or 0) * 80)), 2) if m60_slope is not None else None, "display": f"{m60_slope:+.3f}%" if m60_slope is not None else "数据不足", "state": "up" if m60_slope is not None and m60_slope > 0 else "down" if m60_slope is not None else "insufficient"},
        {"key": "ma20Position", "name": "MA20位置", "score": round(max(0, min(100, 50 + (ma20_bias or 0) * 5)), 2) if ma20_bias is not None else None, "display": f"{ma20_bias:+.2f}%" if ma20_bias is not None else "数据不足", "state": "above" if ma20_bias is not None and ma20_bias > 0 else "below" if ma20_bias is not None else "insufficient"},
        {"key": "rsi14", "name": "RSI(14)", "score": round(current_rsi, 2) if current_rsi is not None else None, "display": f"{current_rsi:.2f}" if current_rsi is not None else "数据不足", "state": "overbought" if current_rsi is not None and current_rsi >= 70 else "oversold" if current_rsi is not None and current_rsi <= 30 else "neutral" if current_rsi is not None else "insufficient"},
        {"key": "macd", "name": "MACD动能", "score": round(max(0, min(100, 50 + (macd_strength or 0) * 25)), 2) if macd_strength is not None else None, "display": f"柱 {momentum['histogram'][-1]:+.4f}", "state": momentum["state"]},
        {"key": "volume", "name": "量能状态", "score": 68.0 if volume_state == "expanding" else 38.0 if volume_state == "contracting" else None, "display": "放量" if volume_state == "expanding" else "缩量" if volume_state == "contracting" else "数据不足", "state": volume_state},
    ]
    conclusion_label = "数据不足" if len(clean) < 60 else "条件偏强" if met == 4 else "中性观察" if met >= 2 else "条件偏弱"
    conclusion_tone = "missing" if len(clean) < 60 else "positive" if met == 4 else "watch" if met >= 2 else "negative"
    return {
        "m60": {"value": ma60, "state": "above" if ma60 is not None and latest > ma60 else "below" if ma60 is not None else "insufficient", "direction": "up" if ma60 is not None and ma60_previous is not None and ma60 > ma60_previous else "down" if ma60 is not None and ma60_previous is not None else "insufficient"},
        "ma20": {"value": ma20, "state": "above" if ma20 is not None and latest > ma20 else "below" if ma20 is not None else "insufficient"},
        "rsi": {"value": current_rsi, "state": "overbought" if current_rsi is not None and current_rsi >= 70 else "oversold" if current_rsi is not None and current_rsi <= 30 else "neutral" if current_rsi is not None else "insufficient"},
        "macd": {"dif": momentum["dif"][-1], "dea": momentum["dea"][-1], "histogram": momentum["histogram"][-1], "state": momentum["state"]},
        "volume": {"state": volume_state}, "verdict": verdict,
        "reason": f"M60位置、方向、RSI与MACD共满足 {met}/4 项；数据变化时重新计算。",
        "dataQuality": "complete" if len(clean) >= 60 else "partial",
        "featureProfile": feature_profile,
        "conclusion": {
            "label": conclusion_label,
            "tone": conclusion_tone,
            "score": round(met / 4 * 100, 2) if len(clean) >= 60 else None,
            "summary": f"四项核心条件满足 {met}/4；当前仅用于观察优先级，不构成买卖结论。" if len(clean) >= 60 else "有效日线不足 60 个交易日，暂不形成结论。",
        },
    }


def chart_indicators(rows: list[dict]) -> dict:
    closes = [row.get("close") for row in rows]
    result = {f"ma{period}": moving_average_series(closes, period) for period in (5, 10, 20, 60)}
    result["macd"] = macd(closes)
    return result


def trend_assessment(closes) -> dict:
    clean = _clean(closes)
    if len(clean) < 60:
        return {"score": None, "state": "数据不足", "timeframe": "中期日线", "evidence": []}
    ma5, ma10, ma20, ma60 = (sma(clean, p) for p in (5, 10, 20, 60))
    ordering = 35 if ma5 > ma10 > ma20 > ma60 else -35 if ma5 < ma10 < ma20 < ma60 else 0
    position = 30 if clean[-1] > ma60 else -30
    momentum = 35 if macd(clean)["state"] in {"golden", "above"} else -35
    score = max(-100, min(100, ordering + position + momentum))
    return {"score": score, "state": "上涨" if score > 35 else "下降" if score < -35 else "震荡", "timeframe": "中期日线", "evidence": [{"name": "均线排列", "score": ordering}, {"name": "M60位置", "score": position}, {"name": "MACD", "score": momentum}]}


def percentile_rank(values, current=None) -> float | None:
    """Return an empirical percentile in [0, 100] without inventing missing observations."""
    clean = _clean(values)
    target = clean[-1] if current is None else float(current)
    if not math.isfinite(target) or len(clean) < 20:
        return None
    below = sum(value < target for value in clean)
    equal = sum(value == target for value in clean)
    return round((below + .5 * equal) / len(clean) * 100, 4)


def market_temperature(sector_changes, index_changes, index_full_scale: float = 2.0) -> dict:
    """PDF overview formula: sector breadth * .6 + average index strength * .4."""
    sectors = _clean(sector_changes) if sector_changes else []
    indices = _clean(index_changes) if index_changes else []
    sector_breadth = (sum(value > 0 for value in sectors) - sum(value < 0 for value in sectors)) / len(sectors) if sectors else None
    index_average = fmean(indices) if indices else None
    index_strength = max(-1.0, min(1.0, index_average / index_full_scale)) if index_average is not None else None
    components = [(sector_breadth, .6), (index_strength, .4)]
    available = [(value, weight) for value, weight in components if value is not None]
    weight = sum(item[1] for item in available)
    raw = sum(value * item_weight for value, item_weight in available) / weight if weight else None
    score = round((raw + 1) * 50, 2) if raw is not None else None
    state = "数据不足" if raw is None else "普涨" if raw >= .55 else "偏强" if raw >= .18 else "震荡分化" if raw > -.18 else "偏弱" if raw > -.55 else "普跌"
    return {
        "score": score, "raw": round(raw, 4) if raw is not None else None, "state": state,
        "coverage": round(weight, 4), "formula": "sectorBreadth*0.6 + indexAverageStrength*0.4",
        "components": {"sectorBreadth": round(sector_breadth, 4) if sector_breadth is not None else None, "indexAveragePercent": round(index_average, 4) if index_average is not None else None, "indexStrength": round(index_strength, 4) if index_strength is not None else None},
    }


def technical_top_inputs(rows: list[dict]) -> dict[str, float | None]:
    """Derive the PDF momentum/volatility inputs from one chronological K-line series."""
    closes = [row.get("close") for row in rows]
    volumes = [row.get("volume") for row in rows]
    clean_close = _clean(closes)
    clean_volume = _clean(volumes)
    if len(clean_close) < 80:
        return {"rsi": None, "maBiasPercentile": None, "macdDivergence": None, "volumePriceDivergence": None, "realizedVolatilityPercentile": None, "aboveM60": None, "volumePercentile": None}
    ma60_series = moving_average_series(clean_close, 60)
    biases = [abs(close / average - 1) for close, average in zip(clean_close, ma60_series) if average]
    ma_bias = percentile_rank(biases[-120:]) if len(biases) >= 20 else None
    momentum = macd(clean_close)
    lookback = min(40, len(clean_close) - 1)
    midpoint = max(2, lookback // 2)
    recent_price = clean_close[-midpoint:]
    prior_price = clean_close[-lookback:-midpoint]
    recent_dif = momentum["dif"][-midpoint:]
    prior_dif = momentum["dif"][-lookback:-midpoint]
    bearish_divergence = bool(prior_price and prior_dif and max(recent_price) > max(prior_price) and max(recent_dif) < max(prior_dif))
    price_change = clean_close[-1] / clean_close[-21] - 1 if len(clean_close) >= 21 else 0
    recent_volume = fmean(clean_volume[-10:]) if len(clean_volume) >= 20 else None
    prior_volume = fmean(clean_volume[-20:-10]) if len(clean_volume) >= 20 else None
    volume_divergence = bool(price_change > 0 and recent_volume is not None and prior_volume and recent_volume < prior_volume * .8)
    returns = [math.log(current / previous) for previous, current in zip(clean_close, clean_close[1:]) if previous > 0 and current > 0]
    rolling_vol = []
    for index in range(19, len(returns)):
        window = returns[index - 19:index + 1]
        mean = fmean(window)
        variance = fmean((value - mean) ** 2 for value in window)
        rolling_vol.append(math.sqrt(variance) * math.sqrt(252))
    vol_percentile = percentile_rank(rolling_vol[-120:]) if len(rolling_vol) >= 20 else None
    return {
        "rsi": rsi(clean_close), "maBiasPercentile": ma_bias,
        "macdDivergence": 90.0 if bearish_divergence else 25.0,
        "volumePriceDivergence": 85.0 if volume_divergence else 25.0,
        "realizedVolatilityPercentile": vol_percentile,
        "aboveM60": 100.0 if ma60_series[-1] is not None and clean_close[-1] > ma60_series[-1] else 0.0,
        "volumePercentile": percentile_rank(clean_volume[-120:]) if len(clean_volume) >= 20 else None,
    }


TOP_WEIGHTS = {"valuation": 30, "sentiment": 20, "momentum": 20, "breadth": 20, "volatility": 10}

TOP_INDICATORS = {
    "valuation": (("broadPePercentile", "宽基PE-TTM分位", .50, False), ("growthDividendPercentile", "成长/红利比值分位", .25, False), ("buffettIndicatorPercentile", "巴菲特指标分位", .25, True)),
    "sentiment": (("chinextTurnoverPercentile", "创业板换手率分位", .25, False), ("shanghaiVolumePercentile", "上证量能分位", .25, False), ("marginHeat", "融资余额热度", .30, True), ("retailAccountsPercentile", "新增开户分位", .20, True)),
    "momentum": (("rsiHeat", "RSI均值", .30, False), ("maBiasPercentile", "均线乖离分位", .25, False), ("macdDivergenceHeat", "MACD顶背离", .25, False), ("volumePriceDivergenceHeat", "量价背离", .20, False)),
    "breadth": (("advancingRatio", "上涨广度", .55, False), ("aboveM60Ratio", "站上M60占比", .45, False)),
    "volatility": (("realizedVolatilityPercentile", "真实波动率分位", 1.0, False),),
}


def comprehensive_top_observer(inputs: dict[str, float | None], sources: dict[str, str] | None = None) -> dict:
    """Complete five-dimension model with transparent automatic/manual coverage."""
    sources = sources or {}
    dimension_values: dict[str, float | None] = {}
    detail: dict[str, dict] = {}
    for dimension, definitions in TOP_INDICATORS.items():
        rows, weighted, available_weight = [], 0.0, 0.0
        for key, label, weight, manual in definitions:
            raw = inputs.get(key)
            value = float(raw) if raw is not None and math.isfinite(float(raw)) else None
            heat = None
            if value is not None:
                heat = max(0.0, min(100.0, 100 - value if dimension == "volatility" and value <= 55 else 55 if dimension == "volatility" else value))
                weighted += heat * weight
                available_weight += weight
            rows.append({"key": key, "name": label, "value": value, "heat": round(heat, 2) if heat is not None else None, "weight": weight, "manual": manual, "source": sources.get(key), "available": value is not None})
        dimension_values[dimension] = round(weighted / available_weight, 2) if available_weight else None
        automatic = [row for row in rows if not row["manual"]]
        manual_rows = [row for row in rows if row["manual"]]
        detail[dimension] = {
            "heat": dimension_values[dimension], "indicators": rows,
            "coverage": round(available_weight, 4),
            "autoDone": sum(row["available"] for row in automatic), "autoTotal": len(automatic),
            "manualDone": sum(row["available"] for row in manual_rows), "manualTotal": len(manual_rows),
            "missing": [row["name"] for row in rows if not row["available"]],
        }
    result = market_top_observer(dimension_values)
    result.update({"dimensionDetails": detail, "model": "pdf-five-dimension.v1", "formula": TOP_WEIGHTS})
    return result


def market_top_observer(dimensions: dict[str, float | None]) -> dict:
    available = {name: float(value) for name, value in dimensions.items() if name in TOP_WEIGHTS and value is not None and math.isfinite(float(value))}
    coverage = sum(TOP_WEIGHTS[name] for name in available) / 100
    denominator = sum(TOP_WEIGHTS[name] for name in available)
    score = round(sum(max(0, min(100, value)) * TOP_WEIGHTS[name] for name, value in available.items()) / denominator, 2) if denominator else None
    levels = {name: "危险" if value >= 70 else "警惕" if value >= 50 else "安全" for name, value in available.items()}
    danger = sum(value == "危险" for value in levels.values())
    conclusion = "insufficient" if coverage < .6 else "danger" if score is not None and score >= 70 and danger >= 2 else "warning" if score is not None and score >= 50 else "safe"
    labels = {"insufficient": "数据不足", "danger": "危险", "warning": "警惕", "safe": "安全"}
    return {"score": score, "coverage": round(coverage, 4), "dimensions": dimensions, "levels": levels, "dangerCount": danger, "version": "top-observer.v2", "conclusion": conclusion, "conclusionLabel": labels[conclusion], "note": "单一维度极端不会直接形成顶部结论"}


def six_dimension_signals(valuation=None, sentiment=None, momentum=None, breadth=None, volatility=None, fund_flow=None) -> list[dict]:
    values = {"估值": valuation, "情绪": sentiment, "技术": momentum, "宽度": breadth, "波动率": volatility, "资金": fund_flow}
    return [{"name": name, "value": value, "signal": "neutral" if value is None else "bear" if value >= 70 else "bull" if value <= 30 else "neutral", "summary": "数据不足" if value is None else f"热度 {value:.1f}/100"} for name, value in values.items()]
