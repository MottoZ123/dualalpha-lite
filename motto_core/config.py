from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CONFIG = ROOT / "motto-config.json"


@dataclass(frozen=True)
class Instrument:
    code: str
    name: str
    market: str
    asset_type: str = "equity"
    original: bool = False
    benchmark_code: str | None = None
    benchmark_name: str | None = None
    benchmark_formula: str | None = None
    benchmark_source_url: str | None = None


@dataclass(frozen=True)
class MottoConfig:
    name: str = "Motto Stock-Analysis"
    timezone: str = "Asia/Shanghai"
    currency: str = "CNY"
    portfolio_mode: str = "none"
    portfolio_interface_enabled: bool = True
    vibe_enabled: bool = False
    vibe_mode: str = "supplement"
    port: int = 8910
    refresh_seconds: dict[str, int] = field(default_factory=lambda: {
        "quote": 10, "intraday": 30, "market": 60, "fund_flow": 120,
        "news": 180, "kline": 300, "fund": 300, "valuation": 3600,
    })
    universe: tuple[Instrument, ...] = ()


ORIGINAL_UNIVERSE = (
    Instrument("300308", "中际旭创", "CN", original=True),
    Instrument("300502", "新易盛", "CN", original=True),
    Instrument("300857", "协创数据", "CN", original=True),
    Instrument("688008", "澜起科技", "CN", original=True),
    Instrument("688257", "新锐股份", "CN", original=True),
    Instrument("688313", "仕佳光子", "CN", original=True),
    Instrument("301297", "富乐德", "CN", original=True),
    Instrument("600522", "中天科技", "CN", original=True),
    Instrument("002335", "科华数据", "CN", original=True),
    Instrument("000657", "中钨高新", "CN", original=True),
    Instrument("601899", "紫金矿业", "CN", original=True),
)

DEFAULT_ADDITIONS = (
    Instrument("000001", "上证指数", "CN", "index"),
    Instrument("399001", "深证成指", "CN", "index"),
    Instrument("399006", "创业板指", "CN", "index"),
    Instrument("000688", "科创50", "CN", "index"),
    Instrument("510300", "沪深300ETF", "CN", "etf"),
    Instrument("159920", "恒生ETF", "CN", "etf"),
    Instrument("513100", "纳指ETF", "CN", "etf"),
    Instrument("00700", "腾讯控股", "HK", "equity"),
    Instrument("AAPL", "Apple", "US", "equity"),
)


def load_motto_config(path: Path = PUBLIC_CONFIG) -> MottoConfig:
    base = MottoConfig(universe=ORIGINAL_UNIVERSE + DEFAULT_ADDITIONS)
    if not path.exists():
        return base
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("portfolio_mode", "none") not in {"none", "basic", "fund_lookthrough"}:
        raise ValueError("portfolio_mode must be none, basic, or fund_lookthrough")
    configured = []
    for item in raw.get("universe", []):
        configured.append(Instrument(
            code=str(item["code"]).strip().upper(), name=str(item["name"]).strip(),
            market=str(item.get("market", "CN")).upper(),
            asset_type=str(item.get("asset_type", "equity")), original=bool(item.get("original")),
            benchmark_code=item.get("benchmark_code"), benchmark_name=item.get("benchmark_name"),
            benchmark_formula=item.get("benchmark_formula"), benchmark_source_url=item.get("benchmark_source_url"),
        ))
    merged = {item.code: item for item in ORIGINAL_UNIVERSE}
    merged.update({item.code: item for item in configured or DEFAULT_ADDITIONS})
    return MottoConfig(
        portfolio_mode=raw.get("portfolio_mode", "none"),
        portfolio_interface_enabled=bool(raw.get("portfolio_interface_enabled", True)),
        vibe_enabled=bool(raw.get("vibe", {}).get("enabled", False)),
        vibe_mode=str(raw.get("vibe", {}).get("mode", "supplement")),
        port=int(raw.get("port", 8910)),
        refresh_seconds={**base.refresh_seconds, **raw.get("refresh_seconds", {})},
        universe=tuple(merged.values()),
    )
