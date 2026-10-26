from __future__ import annotations

from datetime import datetime
import re
from typing import Iterable

import requests

from .config import Instrument
from .contracts import DataMeta, envelope, finite_number


class ProviderError(RuntimeError):
    pass


def tencent_symbol(item: Instrument) -> str:
    if item.market == "HK":
        return f"hk{item.code.zfill(5)}"
    if item.market == "US":
        return f"us{item.code.upper()}"
    if item.asset_type == "index":
        if item.code.startswith("399"):
            return f"sz{item.code}"
        return f"sh{item.code}"
    return f"sh{item.code}" if item.code.startswith(("5", "6", "9")) else f"sz{item.code}"


class TencentMarketProvider:
    name = "tencent-market"

    def __init__(self, session=requests, timeout: int = 10):
        self.session = session
        self.timeout = timeout

    def quotes(self, instruments: Iterable[Instrument]) -> dict:
        items = list(instruments)
        if not items:
            return envelope([], DataMeta.now(self.name))
        symbols = [tencent_symbol(item) for item in items]
        try:
            response = self.session.get(
                "https://qt.gtimg.cn/q=" + ",".join(symbols),
                headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            response.encoding = "gbk"
        except requests.RequestException as exc:
            raise ProviderError(f"Tencent quote unavailable: {exc}") from exc
        lookup = dict(zip(symbols, items))
        result = []
        for line in response.text.splitlines():
            if "=" not in line:
                continue
            symbol = line.split("=", 1)[0].replace("v_", "").strip()
            raw = line.split('"', 2)[1] if '"' in line else ""
            fields = raw.split("~")
            item = lookup.get(symbol)
            if not item or len(fields) < 6:
                continue
            price = finite_number(fields[3])
            previous = finite_number(fields[4])
            change = finite_number(fields[31] if len(fields) > 31 else None)
            pct = finite_number(fields[32] if len(fields) > 32 else None)
            market_time = fields[30] if len(fields) > 30 and fields[30] else None
            result.append({
                "code": item.code, "name": fields[1] or item.name, "market": item.market,
                "assetType": item.asset_type, "original": item.original, "price": price,
                "previousClose": previous, "change": change, "changePercent": pct,
                "marketTime": market_time, "currency": "HKD" if item.market == "HK" else "USD" if item.market == "US" else "CNY",
                "turnoverAmount": finite_number(fields[37] if len(fields) > 37 else None),
                "turnoverAmountUnit": "10k-market-currency",
                "delayLabel": "延迟行情" if item.market == "HK" else None,
            })
        if not result:
            raise ProviderError("Tencent quote response contained no valid instruments")
        return envelope(result, DataMeta.now(self.name, market_time=max((x["marketTime"] or "" for x in result), default=None)))

    def search(self, query: str, limit: int = 8) -> dict:
        """Search Tencent's public symbol suggestion feed for user-entered names/codes."""
        needle = str(query).strip()
        if not needle:
            return envelope([], DataMeta.now("tencent-symbol-search"))
        try:
            response = self.session.get(
                "https://smartbox.gtimg.cn/s3/",
                params={"q": needle, "t": "all"},
                headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            response.encoding = "gbk"
        except requests.RequestException as exc:
            raise ProviderError(f"Tencent symbol search unavailable: {exc}") from exc
        payload = response.text.split('"', 2)[1] if '"' in response.text else response.text
        records = []
        for raw in payload.split("^"):
            fields = raw.split("~")
            if len(fields) < 3:
                continue
            prefix, code, name = fields[0].lower(), fields[1].strip().upper(), fields[2].strip()
            # Smartbox occasionally returns literal JSON-style Unicode escapes
            # inside its legacy GBK payload (for example ``\\u4e2d``). Decode
            # only those escapes so already-decoded Chinese text stays intact.
            name = re.sub(
                r"\\u([0-9a-fA-F]{4})",
                lambda match: chr(int(match.group(1), 16)),
                name,
            )
            if prefix in {"sh", "sz", "bj"}:
                market = "CN"
            elif prefix == "hk":
                market = "HK"
            elif prefix == "us":
                market = "US"
            else:
                continue
            if not code or not name:
                continue
            records.append({"code": code, "name": name, "market": market, "assetType": "equity"})
            if len(records) >= max(1, min(int(limit), 20)):
                break
        return envelope(records, DataMeta.now("tencent-symbol-search"))

    def health(self) -> dict:
        return {"provider": self.name, "configured": True, "authorization": "verify-before-production"}

    def kline(self, item: Instrument, period: str = "day", limit: int = 120) -> dict:
        period = period if period in {"day", "week", "month"} else "day"
        limit = max(20, min(int(limit), 500))
        symbol = tencent_symbol(item)
        try:
            response = self.session.get(
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={"param": f"{symbol},{period},,,{limit},qfq"},
                headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}, timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"Tencent kline unavailable: {exc}") from exc
        bucket = payload.get("data", {}).get(symbol, {})
        rows = bucket.get("usfq" + period) or bucket.get("qfq" + period) or bucket.get(period) or []
        normalized = []
        for row in rows:
            if len(row) < 6:
                continue
            normalized.append({"date": row[0], "open": finite_number(row[1]), "close": finite_number(row[2]), "high": finite_number(row[3]), "low": finite_number(row[4]), "volume": finite_number(row[5])})
        if not normalized:
            raise ProviderError("Tencent kline response contained no valid rows")
        return envelope(normalized, DataMeta.now(self.name, market_time=normalized[-1]["date"], schema_version="market.kline.v1"))

    def intraday(self, item: Instrument) -> dict:
        symbol = tencent_symbol(item)
        try:
            response = self.session.get(
                "https://web.ifzq.gtimg.cn/appstock/app/minute/query",
                params={"code": symbol}, headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}, timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"Tencent intraday unavailable: {exc}") from exc
        rows = payload.get("data", {}).get(symbol, {}).get("data", {}).get("data", [])
        normalized = []
        previous_cumulative = 0.0
        for row in rows:
            values = row.split() if isinstance(row, str) else row
            if len(values) >= 2:
                cumulative = finite_number(values[2] if len(values) > 2 else None)
                incremental = max(0.0, cumulative - previous_cumulative) if cumulative is not None else None
                if cumulative is not None:
                    previous_cumulative = cumulative
                normalized.append({"time": values[0], "price": finite_number(values[1]), "volume": incremental, "cumulativeVolume": cumulative})
        if not normalized:
            raise ProviderError("Tencent intraday response contained no valid rows")
        return envelope(normalized, DataMeta.now(self.name, market_time=normalized[-1]["time"], schema_version="market.intraday.v1"))
