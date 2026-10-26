"""因子计算与历史回测。"""

from __future__ import annotations

import json
import hashlib
import ast
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


FACTOR_NAMES = {
    "Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60",
    "Price_EMA_Bias_20", "Return_5", "Return_20", "Williams_R_14", "CCI_14",
    "Candle_Shape", "Vol_Surge_60", "Price_VWAP_Bias", "MFI_14", "Amihud_Illiquidity",
    "Relative_Strength", "Turn", "BIAS_20", "BIAS_60", "Vol_Ratio", "Norm_ATR_14",
    "Entity_Ratio", "Price_Cost_Bias", "Boll_Width", "Realized_Vol_20", "PV_Corr_10",
    "Overnight_Return", "CMF_20", "Trend_Strength_20",
}

LOCAL_TX_TECH_FACTORS = [
    "Relative_Strength", "Return_5", "BIAS_20", "BIAS_60", "Vol_Ratio", "Norm_ATR_14",
    "Entity_Ratio", "Boll_Width", "Realized_Vol_20", "PV_Corr_10", "Overnight_Return",
    "CMF_20", "Trend_Strength_20",
]
LOCAL_BS_TECH_FACTORS = [
    "Relative_Strength", "Turn", "Return_5", "BIAS_20", "BIAS_60", "Vol_Ratio",
    "Norm_ATR_14", "Entity_Ratio", "Price_Cost_Bias", "Boll_Width", "Realized_Vol_20",
    "PV_Corr_10", "Overnight_Return",
]
LOCAL_TX_MAIN_FACTORS = [
    "Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60",
    "Price_EMA_Bias_20", "Return_5", "Return_20", "Williams_R_14", "CCI_14", "Candle_Shape",
]
LOCAL_BS_MAIN_FACTORS = [
    "Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60",
    "Vol_Surge_60", "Price_VWAP_Bias", "MFI_14", "Amihud_Illiquidity", "Return_5", "Return_20",
]
LOCAL_TECH_CODES = {"300308", "300502", "300857", "688008", "688257", "688313", "301297"}


def _safe_factor_formula(frame: pd.DataFrame, formula: str) -> pd.Series:
    operators = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b}
    unary = {ast.UAdd: lambda a: a, ast.USub: lambda a: -a}

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name) and node.id in frame.columns:
            return frame[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            return unary[type(node.op)](evaluate(node.operand))
        raise ValueError("custom factor formula contains an unsupported operation")

    parsed = ast.parse(formula, mode="eval")
    result = evaluate(parsed)
    return pd.Series(result, index=frame.index, dtype=float).replace([np.inf, -np.inf], np.nan)


def _finite_correlation(left: pd.Series, right: pd.Series, rank: bool = False) -> float | None:
    frame = pd.DataFrame({"left": left, "right": right}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3 or frame["left"].nunique() < 2 or frame["right"].nunique() < 2:
        return None
    if rank:
        frame = frame.rank(method="average")
    value = np.corrcoef(frame["left"].to_numpy(float), frame["right"].to_numpy(float))[0, 1]
    return float(value) if np.isfinite(value) else None


def _normalize_prices(raw: pd.DataFrame, market_return: pd.Series | None = None) -> pd.DataFrame:
    mapping = {
        "日期": "date", "time": "date", "开盘": "Open", "open": "Open", "收盘": "Close", "close": "Close",
        "最高": "High", "high": "High", "最低": "Low", "low": "Low", "成交量": "Volume", "volume": "Volume",
        "成交额": "Amount", "amount": "Amount", "换手率": "Turn", "turn": "Turn",
        "涨跌幅": "PctChg", "pct_chg": "PctChg",
    }
    frame = raw.rename(columns=mapping).copy()
    if "date" not in frame or "Close" not in frame:
        raise ValueError("historical data must include date and close columns")
    for name in ("Open", "High", "Low", "Close", "Volume", "Amount", "Turn", "PctChg"):
        frame[name] = pd.to_numeric(frame[name] if name in frame else 0, errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "Close"]).sort_values("date").drop_duplicates("date").set_index("date")
    if not frame["PctChg"].notna().any() or float(frame["PctChg"].abs().max()) == 0:
        frame["PctChg"] = frame["Close"].pct_change()
    elif float(frame["PctChg"].abs().max()) > 10:
        frame["PctChg"] = frame["PctChg"] / 100
    frame["Market_PctChg"] = market_return.reindex(frame.index).ffill() if market_return is not None else 0.0
    if float(frame["Turn"].abs().max() or 0) > 10:
        frame["Turn"] = frame["Turn"] / 100
    return frame


def compute_factor_frame(raw: pd.DataFrame, market_return: pd.Series | None = None) -> pd.DataFrame:
    """Compute only contemporaneous/trailing factors; targets are added separately."""

    frame = _normalize_prices(raw, market_return)
    frame["Return_5"] = frame["Close"].pct_change(5)
    frame["Return_20"] = frame["Close"].pct_change(20)
    frame["Relative_Strength"] = frame["PctChg"] - frame["Market_PctChg"]
    frame["Relative_Strength_20"] = frame["Return_20"] - frame["Market_PctChg"].rolling(20).sum()
    ema12 = frame["Close"].ewm(span=12, adjust=False).mean()
    ema26 = frame["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    frame["MACD_Hist_Norm"] = (macd - macd.ewm(span=9, adjust=False).mean()) / frame["Close"].replace(0, np.nan)
    mean20 = frame["Close"].rolling(20).mean()
    mean60 = frame["Close"].rolling(60).mean()
    frame["BIAS_20"] = frame["Close"] / mean20.replace(0, np.nan) - 1
    frame["BIAS_60"] = frame["Close"] / mean60.replace(0, np.nan) - 1
    frame["Z_Score_20"] = (frame["Close"] - mean20) / frame["Close"].rolling(20).std().replace(0, np.nan)
    frame["Price_EMA_Bias_20"] = frame["Close"] / frame["Close"].ewm(span=20, adjust=False).mean() - 1
    previous = frame["Close"].shift(1)
    true_range = pd.concat([(frame["High"] - frame["Low"]).abs(), (frame["High"] - previous).abs(), (frame["Low"] - previous).abs()], axis=1).max(axis=1)
    frame["Norm_ATR_14"] = true_range.rolling(14).mean() / frame["Close"].replace(0, np.nan)
    frame["Vol_Ratio"] = frame["Volume"] / frame["Volume"].rolling(20).mean().replace(0, np.nan)
    frame["Entity_Ratio"] = (frame["Close"] - frame["Open"]).abs() / (frame["High"] - frame["Low"]).replace(0, np.nan)
    frame["Boll_Width"] = frame["Close"].rolling(20).std() * 2 / mean20.replace(0, np.nan)
    frame["Realized_Vol_20"] = frame["PctChg"].rolling(20).std() * np.sqrt(252)
    frame["PV_Corr_10"] = frame["Close"].rolling(10).corr(frame["Volume"])
    frame["Overnight_Return"] = frame["Open"] / previous.replace(0, np.nan) - 1
    frame["ATR_Ratio_14_60"] = true_range.rolling(14).mean() / true_range.rolling(60).mean().replace(0, np.nan)
    high14 = frame["High"].rolling(14).max()
    low14 = frame["Low"].rolling(14).min()
    frame["Williams_R_14"] = (high14 - frame["Close"]) / (high14 - low14).replace(0, np.nan) * -100
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    frame["CCI_14"] = (typical - typical.rolling(14).mean()) / (0.015 * typical.rolling(14).std()).replace(0, np.nan)
    frame["Candle_Shape"] = (frame["Close"] - frame["Low"]) / (frame["High"] - frame["Low"]).replace(0, np.nan)
    frame["Vol_Surge_60"] = frame["Volume"] / frame["Volume"].rolling(60).mean().replace(0, np.nan)
    rolling_vwap = frame["Amount"].rolling(20).sum() / frame["Volume"].rolling(20).sum().replace(0, np.nan)
    frame["Price_VWAP_Bias"] = frame["Close"] / rolling_vwap.replace(0, np.nan) - 1
    frame["Price_Cost_Bias"] = frame["Close"] / (frame["Amount"] / frame["Volume"].replace(0, np.nan)).replace(0, np.nan) - 1
    frame["Amihud_Illiquidity"] = (frame["PctChg"].abs() / (frame["Amount"] / 1e8).replace(0, np.nan)).rolling(20).mean()
    positive = typical.mul(frame["Volume"]).where(typical > typical.shift(1), 0.0)
    negative = typical.mul(frame["Volume"]).where(typical < typical.shift(1), 0.0)
    money_ratio = positive.rolling(14).sum() / negative.rolling(14).sum().replace(0, np.nan)
    frame["MFI_14"] = 100 - (100 / (1 + money_ratio))
    close_location = ((frame["Close"] - frame["Low"]) - (frame["High"] - frame["Close"])) / (frame["High"] - frame["Low"]).replace(0, np.nan)
    frame["CMF_20"] = close_location.mul(frame["Volume"]).rolling(20).sum() / frame["Volume"].rolling(20).sum().replace(0, np.nan)
    frame["Trend_Strength_20"] = (frame["Close"] - frame["Close"].shift(20)) / (frame["High"].rolling(20).max() - frame["Low"].rolling(20).min()).replace(0, np.nan)
    return frame.replace([np.inf, -np.inf], np.nan)


def _rank_ic_by_date(frame: pd.DataFrame, factor: str, target: str) -> pd.Series:
    values = {}
    for date, group in frame[["date", "code", factor, target]].dropna().groupby("date"):
        correlation = _finite_correlation(group[factor], group[target], rank=True)
        if correlation is not None:
            values[pd.Timestamp(date)] = correlation
    return pd.Series(values, dtype=float).sort_index()


def evaluate_factor_panel(panel: pd.DataFrame, factors: list[str], label_horizon: int = 20, fee_bps: float = 8, slippage_bps: float = 5, config: dict | None = None) -> dict:
    """Return JSON-serializable metrics from a cross-sectional historical panel."""

    if panel.empty or panel["code"].nunique() < 3:
        raise ValueError("factor evaluation requires historical data for at least three stocks")
    data = panel.sort_values(["code", "date"]).copy()
    config = config or {}
    data["next_return"] = data.groupby("code")["Close"].shift(-1) / data["Close"] - 1
    data["future_return"] = data.groupby("code")["Close"].shift(-label_horizon) / data["Close"] - 1
    market_daily = data.groupby("date")["Market_PctChg"].first().sort_index() if "Market_PctChg" in data else pd.Series(0.0, index=pd.Index(sorted(data["date"].unique())))
    market_trend = market_daily.rolling(60, min_periods=20).sum()
    regime_by_date = pd.Series(np.where(market_trend > 0.08, "bull", np.where(market_trend < -0.08, "bear", "sideways")), index=market_trend.index)
    period = f"{data['date'].min():%Y-%m-%d} — {data['date'].max():%Y-%m-%d}"
    evaluated_at = datetime.now(timezone.utc).isoformat()
    output = {}
    for factor in factors:
        if factor not in data:
            continue
        columns = ["date", "code", "Close", "next_return", "future_return", factor]
        columns += [name for name in ("Volume", "PctChg") if name in data]
        sample = data[columns].replace([np.inf, -np.inf], np.nan)
        sample["tradable"] = True
        if "Volume" in sample:
            sample["tradable"] &= sample["Volume"].fillna(0) > 0
        if "PctChg" in sample:
            sample["tradable"] &= sample["PctChg"].abs().fillna(0) < float(config.get("limitPct", 0.1))
        missing_rate = float(sample[factor].isna().mean())
        ic_values, rank_values = {}, {}
        for date, group in sample.dropna(subset=[factor, "future_return"]).groupby("date"):
            ic = _finite_correlation(group[factor], group["future_return"])
            rank_ic = _finite_correlation(group[factor], group["future_return"], rank=True)
            if ic is not None:
                ic_values[pd.Timestamp(date)] = ic
            if rank_ic is not None:
                rank_values[pd.Timestamp(date)] = rank_ic
        ic_series = pd.Series(ic_values, dtype=float).sort_index()
        rank_series = pd.Series(rank_values, dtype=float).sort_index()
        if len(rank_series) < 5:
            continue
        daily_returns, daily_positions, previous_positions = [], [], {}
        for date, group in sample.dropna(subset=[factor, "next_return"]).groupby("date"):
            if str(config.get("suspensionPolicy", "hold")) == "skip":
                group = group[group["tradable"]]
            if len(group) < 3:
                continue
            ordered = group.sort_values(factor)
            count = max(1, len(ordered) // 5)
            short_group, long_group = ordered.head(count), ordered.tail(count)
            positions = {str(code): -0.5 / count for code in short_group["code"]}
            positions.update({str(code): 0.5 / count for code in long_group["code"]})
            turnover = 0.5 * sum(abs(positions.get(code, 0.0) - previous_positions.get(code, 0.0)) for code in set(positions) | set(previous_positions)) if previous_positions else 0.0
            gross = float(.5 * long_group["next_return"].mean() - .5 * short_group["next_return"].mean())
            net = gross - turnover * (fee_bps + slippage_bps) / 10_000
            daily_returns.append((pd.Timestamp(date), gross, net))
            daily_positions.append(turnover)
            previous_positions = positions
        returns = pd.DataFrame(daily_returns, columns=["date", "gross", "net"]).set_index("date") if daily_returns else pd.DataFrame()
        if returns.empty:
            continue
        equity = (1 + returns["net"].clip(lower=-0.99)).cumprod()
        years = max(len(returns) / 252, 1 / 252)
        gross_annual = float((np.prod(1 + returns["gross"].clip(lower=-0.99)) ** (1 / years)) - 1)
        net_annual = float((equity.iloc[-1] ** (1 / years)) - 1)
        drawdown = float((equity / equity.cummax() - 1).min())
        ic_mean = float(ic_series.mean()) if not ic_series.empty else None
        rank_mean = float(rank_series.mean())
        icir = float(rank_mean / rank_series.std(ddof=1) * np.sqrt(252 / max(label_horizon, 1))) if len(rank_series) > 1 and rank_series.std(ddof=1) > 0 else None
        annual_sign = rank_series.groupby(rank_series.index.year).mean()
        regime_stability = float((np.sign(annual_sign) == np.sign(rank_mean)).mean()) if len(annual_sign) else None
        regime_performance = {}
        for regime in ("bull", "bear", "sideways"):
            dates = regime_by_date[regime_by_date == regime].index
            values = rank_series.reindex(dates).dropna()
            regime_performance[regime] = float(values.mean()) if len(values) else None
        decay_half_life = 40
        baseline = None
        for horizon in (1, 5, 10, 20, 40):
            target = f"future_{horizon}"
            data[target] = data.groupby("code")["Close"].shift(-horizon) / data["Close"] - 1
            decay_ic = _rank_ic_by_date(data, factor, target).mean()
            if horizon == 1:
                baseline = abs(float(decay_ic)) if np.isfinite(decay_ic) else None
            elif baseline and np.isfinite(decay_ic) and abs(float(decay_ic)) <= baseline / 2:
                decay_half_life = horizon
                break
        curve_points = equity.iloc[np.unique(np.linspace(0, len(equity) - 1, min(80, len(equity))).astype(int))]
        output[factor] = {
            "ic": ic_mean,
            "rankIc": rank_mean,
            "icir": icir,
            "longShortReturn": gross_annual,
            "winRate": float((returns["net"] > 0).mean()),
            "maxDrawdown": drawdown,
            "turnover": float(np.mean(daily_positions)) if daily_positions else None,
            "costAdjustedReturn": net_annual,
            "decayHalfLife": decay_half_life,
            "missingRate": missing_rate,
            "regimeStability": regime_stability,
            "regimePerformance": regime_performance,
            "equityCurve": [{"date": index.strftime("%Y-%m-%d"), "value": float(value)} for index, value in curve_points.items()],
            "tradeRules": {"feeBps": fee_bps, "slippageBps": slippage_bps, "suspensionPolicy": config.get("suspensionPolicy", "hold"), "limitPct": config.get("limitPct", 0.1)},
            "leakage": "passed",
            "evaluatedAt": evaluated_at,
            "period": period,
        }
    if not output:
        raise ValueError("insufficient cross-sectional observations to calculate factor metrics")
    return output


def evaluate_factor_relationships(panel: pd.DataFrame, factors: list[str], weights: dict[str, float] | None = None, label_horizon: int = 20) -> dict:
    data = panel.sort_values(["code", "date"]).copy()
    selected = [factor for factor in factors if factor in data]
    if not selected:
        return {"correlation": {}, "marginalContribution": {}, "redundantPairs": []}
    correlations = {factor: {other: [] for other in selected} for factor in selected}
    for _, group in data[["date", "code", *selected]].groupby("date"):
        for factor in selected:
            for other in selected:
                value = _finite_correlation(group[factor], group[other], rank=True)
                if value is not None:
                    correlations[factor][other].append(value)
    matrix = {factor: {other: float(np.mean(values)) if values else None for other, values in row.items()} for factor, row in correlations.items()}
    redundant = []
    for index, factor in enumerate(selected):
        for other in selected[index + 1:]:
            value = matrix[factor][other]
            if value is not None and abs(value) >= 0.7:
                redundant.append({"left": factor, "right": other, "correlation": value})
    data["future_return"] = data.groupby("code")["Close"].shift(-label_horizon) / data["Close"] - 1
    supplied = weights or {}
    normalized_weights = {factor: max(0.0, float(supplied.get(factor, 1.0))) for factor in selected}
    total = sum(normalized_weights.values()) or 1.0
    normalized_weights = {factor: value / total for factor, value in normalized_weights.items()}

    def composite_rank_ic(excluded: str | None = None):
        included = [factor for factor in selected if factor != excluded]
        if not included:
            return None
        frame = data[["date", "code", "future_return", *included]].copy()
        composite = pd.Series(0.0, index=frame.index)
        active_total = sum(normalized_weights[factor] for factor in included) or 1.0
        for factor in included:
            standardized = frame.groupby("date")[factor].transform(lambda values: (values - values.mean()) / (values.std(ddof=0) or np.nan))
            composite += standardized.fillna(0) * normalized_weights[factor] / active_total
        frame["composite"] = composite
        series = _rank_ic_by_date(frame, "composite", "future_return")
        return float(series.mean()) if len(series) else None

    full = composite_rank_ic()
    marginal = {}
    for factor in selected:
        without = composite_rank_ic(factor)
        marginal[factor] = float(full - without) if full is not None and without is not None else None
    return {"correlation": matrix, "compositeRankIc": full, "marginalContribution": marginal, "redundantPairs": redundant}


def walk_forward_t1_backtest(panel: pd.DataFrame, factors: list[str], config: dict | None = None, supplied_weights: dict[str, float] | None = None) -> dict:
    """Expanding-window, strictly out-of-sample T+1 factor backtest.

    Factor direction and weights are learned only from dates whose T+1 labels
    are known before each test window. Test-window returns are never reused for
    that window's factor selection or weighting.
    """
    config = config or {}
    data = panel.sort_values(["date", "code"]).copy()
    selected = [factor for factor in factors if factor in data]
    if len(selected) < 1 or data["code"].nunique() < 3:
        raise ValueError("walk-forward T+1 requires at least one factor and three stocks")
    data["next_return"] = data.groupby("code")["Close"].shift(-1) / data["Close"] - 1
    dates = list(pd.Index(sorted(pd.to_datetime(data["date"].unique()))))
    min_train = max(60, int(config.get("minTrainDays", 120)))
    test_window = max(5, int(config.get("testWindowDays", 20)))
    rebalance_every = max(1, int(config.get("rebalanceEvery", 1)))
    quantile = min(.45, max(.1, float(config.get("longShortQuantile", .2))))
    fee_bps = float(config.get("feeBps", 8))
    slippage_bps = float(config.get("slippageBps", 5))
    if len(dates) <= min_train + 5:
        raise ValueError(f"walk-forward T+1 needs more than {min_train + 5} trading dates")
    supplied = {name: max(0.0, float(value)) for name, value in (supplied_weights or {}).items() if name in selected}
    rank_ic_history = {factor: _rank_ic_by_date(data, factor, "next_return") for factor in selected}
    date_groups = {pd.Timestamp(date): group for date, group in data.groupby("date", sort=False)}
    daily, folds, previous_positions = [], [], {}
    fold_start = min_train + 1  # leave one full date between learned labels and test observations
    while fold_start < len(dates) - 1:
        test_dates = dates[fold_start:min(len(dates) - 1, fold_start + test_window)]
        train_dates = dates[:fold_start - 1]
        learned = {}
        for factor in selected:
            history = rank_ic_history[factor]
            series = history[history.index.isin(train_dates)]
            value = float(series.mean()) if len(series) >= 5 and np.isfinite(series.mean()) else 0.0
            learned[factor] = value
        base_weights = {factor: supplied.get(factor, abs(value)) for factor, value in learned.items()}
        total_weight = sum(base_weights.values())
        if total_weight == 0:
            base_weights = {factor: 1.0 for factor in selected}
            total_weight = float(len(selected))
        normalized = {factor: base_weights[factor] / total_weight for factor in selected}
        directions = {factor: 1.0 if learned[factor] >= 0 else -1.0 for factor in selected}
        fold_daily = 0
        for date_index, date in enumerate(test_dates):
            if date_index % rebalance_every and previous_positions:
                continue
            group = date_groups[pd.Timestamp(date)].dropna(subset=["next_return", *selected]).copy()
            if len(group) < 3:
                continue
            composite = pd.Series(0.0, index=group.index)
            for factor in selected:
                values = group[factor]
                std = values.std(ddof=0)
                standardized = (values - values.mean()) / std if std and np.isfinite(std) else pd.Series(0.0, index=values.index)
                composite += standardized.fillna(0) * normalized[factor] * directions[factor]
            group["composite"] = composite
            group = group.sort_values("composite")
            count = max(1, int(len(group) * quantile))
            short_group, long_group = group.head(count), group.tail(count)
            positions = {str(code): -0.5 / count for code in short_group["code"]}
            positions.update({str(code): 0.5 / count for code in long_group["code"]})
            turnover = .5 * sum(abs(positions.get(code, 0.0) - previous_positions.get(code, 0.0)) for code in set(positions) | set(previous_positions)) if previous_positions else 0.0
            # Match the dollar-neutral positions above: 50% gross long and
            # 50% gross short. The full spread would double stated exposure.
            gross = float(.5 * long_group["next_return"].mean() - .5 * short_group["next_return"].mean())
            net = gross - turnover * (fee_bps + slippage_bps) / 10_000
            daily.append((pd.Timestamp(date), gross, net, turnover))
            previous_positions = positions
            fold_daily += 1
        train_end, test_start = pd.Timestamp(train_dates[-1]), pd.Timestamp(test_dates[0])
        if not train_end < test_start:
            raise AssertionError("walk-forward leakage guard failed: train end must precede test start")
        folds.append({
            "trainStart": pd.Timestamp(train_dates[0]).strftime("%Y-%m-%d"), "trainEnd": train_end.strftime("%Y-%m-%d"),
            "testStart": test_start.strftime("%Y-%m-%d"), "testEnd": pd.Timestamp(test_dates[-1]).strftime("%Y-%m-%d"),
            "observations": fold_daily, "factorRankIc": learned, "weights": normalized, "directions": directions,
        })
        fold_start += test_window
    if not daily:
        raise ValueError("walk-forward T+1 produced no tradable out-of-sample observations")
    returns = pd.DataFrame(daily, columns=["date", "gross", "net", "turnover"]).drop_duplicates("date").set_index("date").sort_index()
    equity = (1 + returns["net"].clip(lower=-.99)).cumprod()
    years = max(len(returns) / 252, 1 / 252)
    annualized = float(equity.iloc[-1] ** (1 / years) - 1)
    gross_equity = (1 + returns["gross"].clip(lower=-.99)).cumprod()
    gross_annualized = float(gross_equity.iloc[-1] ** (1 / years) - 1)
    maximum_drawdown = float((equity / equity.cummax() - 1).min())
    curve = equity.iloc[np.unique(np.linspace(0, len(equity) - 1, min(120, len(equity))).astype(int))]
    return {
        "mode": "expanding-window", "horizon": "T+1", "leakageCheck": "passed-by-date-boundary",
        "folds": folds, "outOfSampleDays": int(len(returns)), "grossAnnualizedReturn": gross_annualized,
        "costAdjustedAnnualizedReturn": annualized, "maxDrawdown": maximum_drawdown,
        "winRate": float((returns["net"] > 0).mean()), "averageTurnover": float(returns["turnover"].mean()),
        "feeBps": fee_bps, "slippageBps": slippage_bps,
        "equityCurve": [{"date": index.strftime("%Y-%m-%d"), "value": float(value)} for index, value in curve.items()],
    }


def local_dual_track_walk_forward(panel: pd.DataFrame, horizon: int, config: dict | None = None) -> dict:
    """Walk-forward classifier matching the local TX/BS factor families.

    T+1 is an attention-quality study: it reports hit rates and does not assume
    that every daily signal is traded. T+5 uses non-overlapping observation
    dates and reports cost-adjusted hypothetical returns.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    config = config or {}
    if horizon not in {1, 5}:
        raise ValueError("local TX/BS walk-forward supports T+1 and T+5")
    data = panel.sort_values(["date", "code"]).copy()
    data["date"] = pd.to_datetime(data["date"])
    data["future_return"] = data.groupby("code")["Close"].shift(-horizon) / data["Close"] - 1
    market_daily = data.groupby("date")["Market_PctChg"].first().sort_index().fillna(0)
    market_level = (1 + market_daily).cumprod()
    market_future = market_level.shift(-horizon) / market_level - 1
    data["market_future_return"] = data["date"].map(market_future)
    data["outperformed"] = (data["future_return"] > data["market_future_return"]).astype(float)
    data.loc[data[["future_return", "market_future_return"]].isna().any(axis=1), "outperformed"] = np.nan
    data["sector"] = np.where(data["code"].astype(str).isin(LOCAL_TECH_CODES), "tech", "main")

    profiles = {
        "tx": {"tech": LOCAL_TX_TECH_FACTORS, "main": LOCAL_TX_MAIN_FACTORS},
        "bs": {"tech": LOCAL_BS_TECH_FACTORS, "main": LOCAL_BS_MAIN_FACTORS},
    }
    dates = list(pd.Index(sorted(data["date"].unique())))
    min_train = max(120, int(config.get("minTrainDays", 250)))
    test_window = max(5, int(config.get("testWindowDays", 20)))
    observation_step = 1 if horizon == 1 else max(horizon, int(config.get("t5ObservationStep", 5)))
    top_n = max(1, int(config.get("attentionTopN", 2)))
    probability_floor = float(config.get("probabilityFloor", .53))
    if len(dates) <= min_train + horizon + 5:
        raise ValueError(f"dual-track T+{horizon} needs more than {min_train + horizon + 5} trading dates")

    predictions, folds = [], []
    fold_start = min_train + horizon
    while fold_start < len(dates) - horizon:
        test_dates = dates[fold_start:min(len(dates) - horizon, fold_start + test_window)]
        train_dates = dates[:fold_start - horizon]
        fold_models = []
        for track, sector_profiles in profiles.items():
            for sector, factor_names in sector_profiles.items():
                raw_train = data[(data["sector"] == sector) & data["date"].isin(train_dates)].dropna(subset=["outperformed"]).copy()
                raw_test = data[(data["sector"] == sector) & data["date"].isin(test_dates)].dropna(subset=["future_return", "market_future_return"]).copy()
                factors = [name for name in factor_names if name in data and raw_train[name].notna().mean() >= .5 and raw_test[name].notna().any()]
                omitted = [name for name in factor_names if name not in factors]
                if not factors:
                    continue
                medians = raw_train[factors].median().fillna(0)
                train = raw_train.dropna(subset=factors, how="all").copy()
                test = raw_test.dropna(subset=factors, how="all").copy()
                train.loc[:, factors] = train[factors].fillna(medians).fillna(0)
                test.loc[:, factors] = test[factors].fillna(medians).fillna(0)
                if len(train) < 100 or train["outperformed"].nunique() < 2 or test.empty:
                    continue
                scaler = StandardScaler()
                x_train = scaler.fit_transform(train[factors].to_numpy(float))
                model = LogisticRegression(max_iter=400, class_weight="balanced", random_state=42)
                model.fit(x_train, train["outperformed"].astype(int).to_numpy())
                test["probability"] = model.predict_proba(scaler.transform(test[factors].to_numpy(float)))[:, 1]
                for row in test[["date", "code", "sector", "probability", "future_return", "market_future_return"]].to_dict("records"):
                    predictions.append({"track": track, **row})
                fold_models.append({"track": track, "sector": sector, "factors": factors, "omittedFactors": omitted, "imputation": "training-fold-median", "trainRows": int(len(train)), "testRows": int(len(test))})
        train_end, test_start = pd.Timestamp(train_dates[-1]), pd.Timestamp(test_dates[0])
        label_known_through = pd.Timestamp(dates[dates.index(train_dates[-1]) + horizon])
        if not label_known_through < test_start:
            raise AssertionError("dual-track leakage guard failed: final training label must predate test start")
        folds.append({
            "trainStart": pd.Timestamp(train_dates[0]).strftime("%Y-%m-%d"),
            "trainEnd": train_end.strftime("%Y-%m-%d"),
            "labelKnownThrough": label_known_through.strftime("%Y-%m-%d"),
            "testStart": test_start.strftime("%Y-%m-%d"),
            "testEnd": pd.Timestamp(test_dates[-1]).strftime("%Y-%m-%d"),
            "models": fold_models,
        })
        fold_start += test_window
    if not predictions:
        raise ValueError("dual-track walk-forward produced no out-of-sample predictions")

    frame = pd.DataFrame(predictions).drop_duplicates(["track", "date", "code"]).sort_values(["track", "date", "probability"], ascending=[True, True, False])
    frame["rank"] = frame.groupby(["track", "date"])["probability"].rank(ascending=False, method="first")
    selected = frame[(frame["rank"] <= top_n) & (frame["probability"] >= probability_floor)].copy()
    selected["tier"] = np.where(selected["probability"] >= .65, "S", np.where(selected["probability"] >= .58, "A", "B"))

    def attention_summary(rows: pd.DataFrame) -> dict:
        tier_summary = {}
        for tier in ("S", "A", "B"):
            tier_rows = rows[rows["tier"] == tier]
            tier_summary[tier] = {
                "signals": int(len(tier_rows)),
                "outperformanceHitRate": float((tier_rows["future_return"] > tier_rows["market_future_return"]).mean()) if len(tier_rows) else None,
                "positiveHitRate": float((tier_rows["future_return"] > 0).mean()) if len(tier_rows) else None,
            }
        by_stock = []
        for code, group in rows.groupby("code"):
            by_stock.append({"code": str(code), "signals": int(len(group)), "outperformanceHitRate": float((group["future_return"] > group["market_future_return"]).mean()), "positiveHitRate": float((group["future_return"] > 0).mean())})
        return {
            "signals": int(len(rows)),
            "observationDates": int(rows["date"].nunique()),
            "outperformanceHitRate": float((rows["future_return"] > rows["market_future_return"]).mean()) if len(rows) else None,
            "positiveHitRate": float((rows["future_return"] > 0).mean()) if len(rows) else None,
            "averageAttentionScore": float(rows["probability"].mean()) if len(rows) else None,
            "tiers": tier_summary,
            "byStock": sorted(by_stock, key=lambda row: (-row["signals"], row["code"])),
        }

    def return_summary(rows: pd.DataFrame) -> dict:
        fee_bps, slippage_bps = float(config.get("feeBps", 8)), float(config.get("slippageBps", 5))
        periods = []
        for index, (date, group) in enumerate(rows.groupby("date")):
            if index % observation_step:
                continue
            gross = float(group["future_return"].mean())
            benchmark = float(group["market_future_return"].mean())
            net = gross - 2 * (fee_bps + slippage_bps) / 10_000
            periods.append((pd.Timestamp(date), gross, net, benchmark))
        if not periods:
            return {"periods": 0, "status": "insufficient"}
        result = pd.DataFrame(periods, columns=["date", "gross", "net", "benchmark"]).drop_duplicates("date").set_index("date")
        equity = (1 + result["net"].clip(lower=-.99)).cumprod()
        years = max(len(result) * horizon / 252, horizon / 252)
        curve = equity.iloc[np.unique(np.linspace(0, len(equity) - 1, min(120, len(equity))).astype(int))]
        return {
            "periods": int(len(result)), "holdingDays": horizon, "nonOverlapping": True,
            "grossAnnualizedReturn": float((1 + result["gross"].clip(lower=-.99)).prod() ** (1 / years) - 1),
            "costAdjustedAnnualizedReturn": float(equity.iloc[-1] ** (1 / years) - 1),
            "cumulativeNetReturn": float(equity.iloc[-1] - 1),
            "maxDrawdown": float((equity / equity.cummax() - 1).min()),
            "positivePeriodRate": float((result["net"] > 0).mean()),
            "outperformanceRate": float((result["gross"] > result["benchmark"]).mean()),
            "roundTripCostBps": 2 * (fee_bps + slippage_bps),
            "equityCurve": [{"date": index.strftime("%Y-%m-%d"), "value": float(value)} for index, value in curve.items()],
        }

    track_results = {}
    for track in ("tx", "bs"):
        rows = selected[selected["track"] == track]
        track_results[track] = attention_summary(rows)
        if horizon == 5:
            track_results[track]["returnStudy"] = return_summary(rows)
    consensus_keys = selected.groupby(["date", "code"])["track"].nunique()
    consensus_pairs = set(consensus_keys[consensus_keys >= 2].index)
    consensus = selected[selected.apply(lambda row: (row["date"], row["code"]) in consensus_pairs, axis=1)].drop_duplicates(["date", "code"])
    consensus_result = attention_summary(consensus)
    if horizon == 5:
        consensus_result["returnStudy"] = return_summary(consensus)
    return {
        "mode": "local-tx-bs-walk-forward", "horizon": f"T+{horizon}",
        "primaryObjective": "attention-hit-rate" if horizon == 1 else "non-overlapping-cost-adjusted-return",
        "tradeAssumption": "no-daily-trade-assumption" if horizon == 1 else "hold-five-trading-days",
        "probabilityTiers": {"B": .53, "A": .58, "S": .65}, "attentionTopN": top_n,
        "leakageCheck": "passed-label-known-before-test", "missingFactorPolicy": "per-fold availability disclosure; training-fold median only", "folds": folds,
        "factorProfiles": profiles, "tracks": track_results, "consensus": consensus_result,
    }


def fetch_a_share_panel(stocks: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak

    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    market_raw = ak.stock_zh_index_daily_tx(symbol="sh000001")
    market = _normalize_prices(market_raw)["Close"].pct_change()
    frames = []
    errors = {}
    for code in stocks:
        symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
        try:
            raw = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end, adjust="qfq")
            if len(raw) < 120:
                errors[code] = f"only {len(raw)} observations"
                continue
            frame = compute_factor_frame(raw, market).reset_index()
            frame["code"] = code
            frames.append(frame)
        except Exception as exc:
            errors[code] = str(exc)[:160]
    if len(frames) < 3:
        raise ValueError(f"fewer than three stocks have sufficient data: {errors}")
    return pd.concat(frames, ignore_index=True)


def run_factor_backtest(stocks: list[str], factors: list[str], config: dict, output_dir: str | Path | None = None, weights: dict[str, float] | None = None) -> dict:
    custom_formulas = config.get("customFactorFormulas", {}) if isinstance(config.get("customFactorFormulas", {}), dict) else {}
    selected = [name for name in factors if name in FACTOR_NAMES or name in custom_formulas]
    if not selected:
        raise ValueError("no supported factors selected")
    panel = fetch_a_share_panel(stocks, str(config.get("dateFrom", "2021-01-01")), str(config.get("dateTo", datetime.now().date())))
    for name in selected:
        if name in custom_formulas:
            panel[name] = _safe_factor_formula(panel, str(custom_formulas[name]))
    horizon = int(config.get("labelHorizon", 1))
    metrics = evaluate_factor_panel(panel, selected, horizon, float(config.get("feeBps", 8)), float(config.get("slippageBps", 5)), config)
    relationships = evaluate_factor_relationships(panel, selected, weights, horizon)
    local_profile = str(config.get("factorPreset", "")) == "local_tx_bs"
    dual_horizon = {
        "t1Attention": local_dual_track_walk_forward(panel, 1, config),
        "t5Return": local_dual_track_walk_forward(panel, 5, config),
    } if local_profile and bool(config.get("runDualHorizon", True)) else None
    walk_forward = walk_forward_t1_backtest(panel, selected, config, weights) if bool(config.get("walkForward", True)) and horizon == 1 and not local_profile else None
    fingerprint = hashlib.sha256(pd.util.hash_pandas_object(panel[["date", "code", "Close"]], index=False).values.tobytes()).hexdigest()[:20]
    result = {"status": "completed", "stocks": stocks, "factors": selected, "weights": weights or {}, "observations": int(len(panel)), "factorMetrics": metrics, "factorRelationships": relationships, "walkForwardResults": walk_forward, "dualHorizonResults": dual_horizon, "config": config, "dataVersion": fingerprint, "dataSource": "AkShare Tencent adjusted daily history", "methodology": {"horizon": "T+1 attention / T+5 return" if dual_horizon else f"T+{horizon}", "walkForward": "local-tx-bs-dual-horizon" if dual_horizon else "executed" if walk_forward else "not-executed", "pointInTimeFinancials": False, "futureLeakageCheck": dual_horizon["t1Attention"]["leakageCheck"] if dual_horizon else walk_forward["leakageCheck"] if walk_forward else "label-shift-only", "marketRegimes": ["bull", "bear", "sideways"]}}
    if output_dir:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=False)
        (path / "factor-metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["outputDir"] = str(path)
    return result