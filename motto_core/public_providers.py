from __future__ import annotations

import threading
import time
import uuid
import csv
import io
import re
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import requests

from .contracts import DataMeta, envelope, finite_number
from .providers import ProviderError


class EastMoneyProvider:
    """Defensive adapters for public Eastmoney market datasets."""

    hosts = ("push2.eastmoney.com", "push2his.eastmoney.com", "push2delay.eastmoney.com")

    def __init__(self, session=requests, timeout: int = 10, min_interval: float = .35):
        self.session, self.timeout, self.min_interval = session, timeout, min_interval
        self._guard, self._last_request = threading.Lock(), 0.0

    def _throttle(self):
        with self._guard:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def _get_json(self, path: str, params: dict[str, Any], hosts=None):
        errors = []
        for host in hosts or self.hosts:
            self._throttle()
            try:
                response = self.session.get(f"https://{host}{path}", params=params, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout=self.timeout)
                response.raise_for_status()
                return response.json(), host
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{host}:{exc}")
        raise ProviderError("Eastmoney hosts unavailable: " + "; ".join(errors)[:320])

    def fund_flows(self, kind: str = "industry", page_size: int = 100, max_pages: int = 8):
        fs = "m:90+t:2+f:!50" if kind == "industry" else "m:90+t:3+f:!50"
        records, used_host = [], None
        for page in range(1, max_pages + 1):
            payload, used_host = self._get_json("/api/qt/clist/get", {"pn": page, "pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f62", "fs": fs, "fields": "f12,f14,f3,f62,f184"})
            rows = (payload.get("data") or {}).get("diff") or []
            for row in rows:
                records.append({"code": str(row.get("f12", "")), "name": str(row.get("f14", "")), "changePercent": finite_number(row.get("f3")), "mainNetInflow": finite_number(row.get("f62")), "mainNetRatio": finite_number(row.get("f184")), "kind": kind})
            if len(rows) < page_size:
                break
        valid = [row for row in records if row["name"] and any(row[key] not in (None, 0) for key in ("changePercent", "mainNetInflow", "mainNetRatio"))]
        if records and not valid:
            raise ProviderError("Eastmoney flow package was all-zero or invalid; keeping last-known-good")
        return envelope(valid, DataMeta.now(f"eastmoney:{used_host}", market_time=datetime.now(timezone.utc).isoformat(), schema_version="market.flow.v1"))

    def market_breadth(self, page_size: int = 500, max_pages: int = 12):
        """Whole-market A-share breadth from atomic quote rows.

        Limit counts use the displayed previous close and board-aware 20%/10%
        thresholds. ST and IPO special limits cannot be inferred safely and are
        therefore disclosed as estimates rather than official exchange counts.
        """
        fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        records, used_host = [], None
        for page in range(1, max_pages + 1):
            payload, used_host = self._get_json("/api/qt/clist/get", {
                "pn": page, "pz": page_size, "po": 1, "np": 1, "fltt": 2,
                "invt": 2, "fid": "f3", "fs": fs,
                "fields": "f2,f3,f12,f14,f18",
            })
            rows = (payload.get("data") or {}).get("diff") or []
            records.extend(rows)
            if len(rows) < page_size:
                break
        parsed = []
        for row in records:
            price, change, previous = finite_number(row.get("f2")), finite_number(row.get("f3")), finite_number(row.get("f18"))
            if price is None or change is None or previous in (None, 0):
                continue
            parsed.append({"code": str(row.get("f12") or ""), "name": str(row.get("f14") or ""), "price": price, "change": change, "previous": previous})
        if records and len(parsed) < max(20, len(records) // 5):
            raise ProviderError("Eastmoney breadth package had insufficient valid atomic rows")
        if not parsed:
            raise ProviderError("Eastmoney breadth package contained no valid rows")
        up = sum(row["change"] > 0 for row in parsed)
        down = sum(row["change"] < 0 for row in parsed)
        flat = len(parsed) - up - down
        def limit_threshold(code: str) -> float:
            return 19.5 if code.startswith(("300", "301", "688")) else 9.5
        limit_up = sum(row["change"] >= limit_threshold(row["code"]) for row in parsed)
        limit_down = sum(row["change"] <= -limit_threshold(row["code"]) for row in parsed)
        pool = None
        try:
            pool = self.limit_pools()["data"]
        except ProviderError:
            pool = None
        data = {
            "total": len(parsed), "up": up, "down": down, "flat": flat,
            "advancingRatio": round(up / len(parsed) * 100, 2),
            "limitUpEstimate": limit_up, "limitDownEstimate": limit_down,
            "limitUp": pool.get("limitUp") if pool else None,
            "limitDown": pool.get("limitDown") if pool else None,
            "brokenLimit": pool.get("brokenLimit") if pool else None,
            "sealRate": pool.get("sealRate") if pool else None,
            "limitMethod": "eastmoney-limit-pools" if pool else "quote-threshold-estimate; excludes ST/IPO special rules",
            "officialLimitPoolAvailable": False,
            "preciseCommercialPoolAvailable": bool(pool),
        }
        return envelope(data, DataMeta.now(f"eastmoney:{used_host}", market_time=datetime.now(timezone.utc).isoformat(), schema_version="market.breadth.v1"))

    def limit_pools(self, day: str | None = None):
        """Exact commercial pool counts; not labelled as exchange-official data."""
        requested_day = (day or datetime.now().strftime("%Y%m%d")).replace("-", "")
        common = {"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt", "Pageindex": 0, "pagesize": 1, "sort": "fbt:asc", "date": requested_day}
        paths = {"limitUp": "/getTopicZTPool", "limitDown": "/getTopicDTPool", "brokenLimit": "/getTopicZBPool"}
        counts, qdates, errors = {}, [], []
        for key, path in paths.items():
            try:
                payload, _ = self._get_json(path, common, hosts=("push2ex.eastmoney.com",))
                data = payload.get("data") or {}
                count = data.get("tc")
                counts[key] = int(count) if count is not None else len(data.get("pool") or [])
                if data.get("qdate"):
                    qdates.append(str(data["qdate"]))
            except (ProviderError, TypeError, ValueError) as exc:
                errors.append({"code": key, "message": str(exc)[:160]})
        if not counts:
            raise ProviderError("Eastmoney limit pools unavailable")
        sealed, broken = counts.get("limitUp"), counts.get("brokenLimit")
        counts["sealRate"] = round(sealed / (sealed + broken) * 100, 2) if sealed is not None and broken is not None and sealed + broken else None
        counts.update({"date": max(qdates) if qdates else requested_day, "requestedDate": requested_day, "scope": "A-share", "classification": "commercial-public-pool"})
        meta = DataMeta.now("eastmoney-limit-pools", source_type="commercial-public-interface", freshness="live", quality="partial" if errors else "normal", fallback=False, schema_version="market.limit-pools.v1", note="精确商业池，不等同于交易所官方统计")
        return envelope(counts, meta, errors)

    def margin_balance(self):
        first, host = self._get_json("/api/data/v1/get", {"reportName": "RPTA_WEB_RZRQ_GGMX", "columns": "DATE,RZYE", "pageNumber": 1, "pageSize": 1, "sortColumns": "DATE", "sortTypes": -1}, hosts=("datacenter-web.eastmoney.com",))
        first_rows = ((first.get("result") or {}).get("data") or [])
        latest_date = str(first_rows[0].get("DATE") or "")[:10] if first_rows else ""
        if not latest_date:
            raise ProviderError("Eastmoney margin response has no latest disclosure date")
        total, count, page_size = 0.0, 0, 500
        for page in range(1, 16):
            payload, _ = self._get_json("/api/data/v1/get", {"reportName": "RPTA_WEB_RZRQ_GGMX", "columns": "DATE,RZYE", "pageNumber": page, "pageSize": page_size, "sortColumns": "DATE", "sortTypes": -1, "filter": f"(DATE='{latest_date}')"}, hosts=("datacenter-web.eastmoney.com",))
            rows = ((payload.get("result") or {}).get("data") or [])
            values = [finite_number(row.get("RZYE")) for row in rows]
            total += sum(value for value in values if value is not None)
            count += sum(value is not None for value in values)
            if len(rows) < page_size:
                break
        if not count:
            raise ProviderError("Eastmoney margin response has no finite balances")
        return envelope({"balance": total, "date": latest_date, "unit": "CNY", "frequency": "daily", "constituentCount": count}, DataMeta.now(f"eastmoney:{host}", freshness="daily", schema_version="market.margin.v1"))

    def news(self, limit: int = 30):
        payload, host = self._get_json("/comm/web/getNewsByColumns", {"client": "web", "biz": "web_news_col", "column": "451", "order": 1, "needInteractData": 0, "page_index": 1, "page_size": min(limit, 50), "req_trace": uuid.uuid4().hex}, hosts=("np-weblist.eastmoney.com",))
        rows = payload.get("data") or payload.get("result") or []
        if isinstance(rows, dict):
            rows = rows.get("list") or rows.get("data") or []
        keywords = {"bull": ("降准", "降息", "回购", "增持", "支持", "超预期"), "bear": ("减持", "处罚", "调查", "亏损", "制裁", "退市"), "focus": ("央行", "证监会", "政治局", "美联储", "英伟达", "OpenAI")}
        records = []
        for row in rows[:limit]:
            title = str(row.get("title") or row.get("Art_Title") or "").strip()
            if not title:
                continue
            tags = [name for name, words in keywords.items() if any(word in title for word in words)]
            records.append({"title": title, "time": row.get("showTime") or row.get("Art_ShowTime") or row.get("date"), "url": row.get("url") or row.get("Art_UniqueUrl"), "tags": tags})
        return envelope(records, DataMeta.now(f"eastmoney:{host}", schema_version="market.news.v1"))


class DanjuanValuationProvider:
    def __init__(self, session=requests, timeout: int = 10):
        self.session, self.timeout = session, timeout

    def valuation(self, code: str):
        try:
            response = self.session.get(f"https://danjuanfunds.com/djapi/index_eva/detail/{code}", headers={"User-Agent": "Xueqiu iPhone 14.0", "Referer": "https://danjuanfunds.com/"}, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"Danjuan valuation unavailable: {exc}") from exc
        data = payload.get("data") or {}
        pe = finite_number(data.get("pe") or data.get("pe_ttm") or data.get("pettm"))
        percentile = finite_number(data.get("pe_percentile") or data.get("pe_percentile_10y") or data.get("pe_quantile"))
        if percentile is not None and percentile <= 1:
            percentile *= 100
        if pe is None or percentile is None:
            raise ProviderError("Danjuan response lacks atomic PE-TTM and percentile fields")
        return envelope({"code": code, "peTtm": pe, "percentile": percentile, "date": data.get("date") or data.get("ts"), "confidence": "high", "kind": "true-pe"}, DataMeta.now("danjuan-index-valuation", freshness="hourly", schema_version="market.valuation.v1"))


class EastMoneyFundProvider:
    def __init__(self, session=requests, timeout: int = 10):
        self.session, self.timeout = session, timeout

    def snapshot(self, code: str, limit: int = 10):
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/"}
        try:
            nav_response = self.session.get("https://api.fund.eastmoney.com/f10/lsjz", params={"fundCode": code, "pageIndex": 1, "pageSize": max(10, min(limit, 40))}, headers=headers, timeout=self.timeout)
            nav_response.raise_for_status()
            nav_payload = nav_response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"Eastmoney fund NAV unavailable: {exc}") from exc
        rows = (nav_payload.get("Data") or {}).get("LSJZList") or []
        history = [{"date": row.get("FSRQ"), "nav": finite_number(row.get("DWJZ")), "accumulatedNav": finite_number(row.get("LJJZ")), "changePercent": finite_number(row.get("JZZZL"))} for row in rows]
        history = [row for row in history if row["date"] and row["nav"] is not None]
        if not history:
            raise ProviderError("Eastmoney fund NAV response contained no valid rows")
        estimate = None
        try:
            estimate_response = self.session.get("https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo", params={"FCODE": code, "deviceid": "Wap", "plat": "Wap", "product": "EFund", "version": "6.3.8"}, headers=headers, timeout=self.timeout)
            estimate_response.raise_for_status()
            raw = estimate_response.json().get("Datas")
            item = raw[0] if isinstance(raw, list) and raw else raw if isinstance(raw, dict) else {}
            estimate = finite_number(item.get("GSZZL"))
        except (requests.RequestException, ValueError):
            estimate = None
        latest = history[0]
        sparkline = list(reversed(history[:limit]))
        return envelope({"code": code, "estimateChangePercent": estimate, "officialNav": latest["nav"], "officialAccumulatedNav": latest["accumulatedNav"], "officialChangePercent": latest["changePercent"], "officialDate": latest["date"], "history": sparkline, "intradaySource": "fund-estimate" if estimate is not None else None, "settlementSource": "official-nav", "note": "估值为空时绝不把昨日净值冒充今日盘中估算；历史涨跌优先使用累计净值口径。"}, DataMeta.now("eastmoney-fund", freshness="estimated" if estimate is not None else "official-close", schema_version="fund.snapshot.v1"))


class InstitutionalMacroProvider:
    """Keyless institutional datasets with per-series failure isolation."""

    FRED_SERIES = {
        "DGS10": ("美国10年期国债收益率", "%", "daily"),
        "FEDFUNDS": ("美国有效联邦基金利率", "%", "monthly"),
        "CPIAUCSL": ("美国CPI", "index", "monthly"),
        "VIXCLS": ("VIX收盘", "index", "daily"),
    }

    def __init__(self, session=requests, timeout: int = 12):
        self.session, self.timeout = session, timeout

    def _latest_csv(self, url: str, value_column: str):
        response = self.session.get(url, headers={"User-Agent": "Motto Stock-Analysis/1.0"}, timeout=self.timeout)
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        for row in reversed(rows):
            value = finite_number(row.get(value_column))
            if value is not None:
                return str(row.get("DATE") or row.get("observation_date") or row.get("TIME_PERIOD") or ""), value
        raise ProviderError(f"No finite observations for {value_column}")

    def fred_series(self, code: str):
        response = self.session.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}", headers={"User-Agent": "Motto Stock-Analysis/1.0"}, timeout=self.timeout)
        response.raise_for_status()
        rows = []
        for row in csv.DictReader(io.StringIO(response.text)):
            value = finite_number(row.get(code))
            day = str(row.get("DATE") or row.get("observation_date") or "")
            if day and value is not None:
                rows.append({"date": day, "value": value})
        if not rows:
            raise ProviderError(f"FRED {code} contained no finite observations")
        return rows

    def macro(self):
        records, errors = [], []
        for code, (name, unit, frequency) in self.FRED_SERIES.items():
            try:
                day, value = self._latest_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}", code)
                records.append({"code": code, "name": name, "value": value, "date": day, "unit": unit, "frequency": frequency, "source": "FRED", "sourceUrl": f"https://fred.stlouisfed.org/series/{code}"})
            except (requests.RequestException, ProviderError, ValueError) as exc:
                errors.append({"code": code, "message": str(exc)[:160]})
        records.append({"code": "CN_GDP_2026_H1", "name": "中国国内生产总值", "value": 695704, "date": "2026-H1", "unit": "亿元", "frequency": "official-release", "source": "国家统计局", "sourceUrl": "https://www.stats.gov.cn/sj/zxfbhjd/202607/t20260716_1964142.html", "note": "版本化官方发布值；不是实时序列"})
        meta = DataMeta.now("institutional-macro", source_type="official-public-data", freshness="mixed", quality="partial" if errors else "normal", fallback=False, schema_version="macro.snapshot.v1", note="FRED逐序列隔离；中国GDP采用国家统计局版本化发布值")
        return envelope(records, meta, errors)

    def fx(self):
        series = {}
        errors = []
        for currency in ("CNY", "USD"):
            try:
                url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A?format=csvdata&startPeriod=2026-01-01"
                day, value = self._latest_csv(url, "OBS_VALUE")
                series[currency] = (day, value)
            except (requests.RequestException, ProviderError, ValueError) as exc:
                errors.append({"code": currency, "message": str(exc)[:160]})
        records = []
        if "CNY" in series and "USD" in series and series["USD"][1]:
            records.append({"pair": "USD/CNY", "value": round(series["CNY"][1] / series["USD"][1], 6), "date": min(series["CNY"][0], series["USD"][0]), "method": "ECB EUR cross-rate", "sourceUrl": "https://data-api.ecb.europa.eu/service/data/EXR/"})
        if not records:
            raise ProviderError("ECB cross-rate unavailable: " + "; ".join(item["message"] for item in errors))
        return envelope(records, DataMeta.now("ECB Data API", source_type="official-public-data", freshness="daily", quality="partial" if errors else "normal", schema_version="fx.snapshot.v1", note="USD/CNY由同日ECB欧元参考汇率交叉计算"), errors)

    def buffett_history(self):
        url = "https://api.worldbank.org/v2/country/CHN/indicator/CM.MKT.LCAP.GD.ZS"
        try:
            response = self.session.get(url, params={"format": "json", "per_page": 100}, headers={"User-Agent": "Motto Stock-Analysis/1.0"}, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"World Bank Buffett history unavailable: {exc}") from exc
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
        history = sorted(({"year": str(row.get("date")), "ratio": finite_number(row.get("value"))} for row in rows), key=lambda row: row["year"])
        history = [row for row in history if row["ratio"] is not None]
        if len(history) < 10:
            raise ProviderError("World Bank Buffett history has insufficient observations")
        latest = history[-1]
        percentile = round(sum(row["ratio"] <= latest["ratio"] for row in history) / len(history) * 100, 2)
        data = {"code": "CM.MKT.LCAP.GD.ZS", "name": "中国上市公司市值/GDP", "latestRatio": latest["ratio"], "latestYear": latest["year"], "historicalPercentile": percentile, "observations": len(history), "history": history, "method": "年末上市境内公司总市值÷GDP；以可得年度样本计算经验分位", "sourceUrl": "https://data.worldbank.org/indicator/CM.MKT.LCAP.GD.ZS?locations=CN"}
        return envelope(data, DataMeta.now("World Bank WDI / WFE", source_type="official-public-data", freshness="annual", schema_version="macro.buffett-history.v1", note="年度历史口径，不与盘中市值混为同一原子记录"))


class SseInvestorAccountsProvider:
    """Official monthly new-account statistics published by SSE."""

    def __init__(self, session=requests, timeout: int = 12):
        self.session, self.timeout = session, timeout

    def snapshot(self, month: str = ""):
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.sse.com.cn/aboutus/publication/monthly/investor/"}
        params = {"sqlId": "COMMON_SSE_TZZ_M_STOCK_ACCT_C", "isPagination": "false", "MDATE": month.replace("-", "")}
        try:
            response = self.session.get("https://query.sse.com.cn/commonQuery.do", params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            rows = response.json().get("result") or []
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"SSE monthly investor accounts unavailable: {exc}") from exc
        records = []
        for row in rows:
            total = finite_number(row.get("PERSON"))
            institution = finite_number(row.get("ORG"))
            term = str(row.get("TERM") or "")
            if re.fullmatch(r"\d{4}\.\d{2}", term) and total is not None:
                records.append({"month": term, "newStockAccounts": round(total + (institution or 0), 4), "individual": total, "institution": institution, "aShareIndividual": finite_number(row.get("A_PERSON")), "aShareInstitution": finite_number(row.get("A_ORG")), "unit": "万户", "disclosureMonth": str(row.get("MDATE") or "")})
        records = [row for row in records if row["newStockAccounts"] > 0]
        if not records:
            raise ProviderError("SSE monthly investor response contained no valid rows")
        values = [row["newStockAccounts"] for row in records]
        latest = records[-1]
        latest["historicalPercentile"] = round(sum(value <= latest["newStockAccounts"] for value in values) / len(values) * 100, 2)
        return envelope({"latest": latest, "history": records, "observations": len(records), "definition": "股票账户新开户数（个人+机构），不是唯一投资者人数"}, DataMeta.now("Shanghai Stock Exchange monthly statistics", source_type="exchange-official-public-data", freshness="monthly", schema_version="market.investor-accounts.v1", note="官方月报，单位万户；账户数与投资者人数不可混用"))


class OfficialExchangeLimitProvider:
    """Adapter for licensed SSE/SZSE STEP snapshots exported as JSON.

    Each configured file may contain aggregate counts or a ``rows`` array with
    lastPrice/upperLimit/lowerLimit/highPrice fields. No public-commercial data
    is accepted by this adapter.
    """

    def __init__(self, paths: tuple[str, ...] | None = None):
        configured = paths or tuple(value for value in (os.getenv("SSE_OFFICIAL_SNAPSHOT_FILE"), os.getenv("SZSE_OFFICIAL_SNAPSHOT_FILE")) if value)
        self.paths = tuple(Path(value) for value in configured)

    @staticmethod
    def _counts(payload: dict[str, Any]):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if all(data.get(key) is not None for key in ("limitUp", "limitDown")):
            return {key: int(data.get(key) or 0) for key in ("limitUp", "limitDown", "brokenLimit")}
        rows = data.get("rows") or []
        limit_up = limit_down = broken = 0
        for row in rows:
            last, upper, lower, high = (finite_number(row.get(key)) for key in ("lastPrice", "upperLimit", "lowerLimit", "highPrice"))
            if last is not None and upper is not None and abs(last - upper) < 1e-8:
                limit_up += 1
            if last is not None and lower is not None and abs(last - lower) < 1e-8:
                limit_down += 1
            if high is not None and upper is not None and abs(high - upper) < 1e-8 and (last is None or abs(last - upper) >= 1e-8):
                broken += 1
        return {"limitUp": limit_up, "limitDown": limit_down, "brokenLimit": broken}

    def snapshot(self):
        if not self.paths:
            raise ProviderError("Official SSE/SZSE STEP snapshot files are not configured")
        total = {"limitUp": 0, "limitDown": 0, "brokenLimit": 0}
        files = []
        for path in self.paths:
            if not path.is_file():
                raise ProviderError(f"Official snapshot not found: {path}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            counts = self._counts(payload)
            for key in total:
                total[key] += counts[key]
            files.append(path.name)
        denominator = total["limitUp"] + total["brokenLimit"]
        total.update({"sealRate": round(total["limitUp"] / denominator * 100, 2) if denominator else None, "files": files, "classification": "licensed-exchange-feed"})
        return envelope(total, DataMeta.now("SSE/SZSE licensed STEP snapshots", source_type="exchange-official-licensed-feed", freshness="live", schema_version="market.limit-pools.official.v1", note="仅接受交易所授权行情网关导出；不接受商业网页数据冒充"))


class CmeOfficialFuturesProvider:
    """Credentialed adapter for a user's CME Group Market Data API subscription."""

    def __init__(self, session=requests, timeout: int = 12, endpoint: str | None = None, api_key: str | None = None):
        self.session, self.timeout = session, timeout
        self.endpoint = endpoint or os.getenv("CME_MARKET_DATA_REST_URL", "")
        self.api_key = api_key or os.getenv("CME_MARKET_DATA_API_KEY", "")

    def snapshot(self):
        if not self.endpoint or not self.api_key:
            raise ProviderError("CME official API subscription is not configured")
        try:
            response = self.session.get(self.endpoint, params={"symbols": "ES,NQ,YM"}, headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json", "User-Agent": "Motto Stock-Analysis/1.0"}, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"CME official market data unavailable: {exc}") from exc
        rows = payload.get("data") or payload.get("quotes") or []
        records = []
        names = {"ES": "E-mini S&P 500", "NQ": "E-mini Nasdaq-100", "YM": "E-mini Dow"}
        for row in rows:
            code = str(row.get("symbol") or row.get("productCode") or "").upper()
            price = finite_number(row.get("last") or row.get("lastPrice"))
            if code in names and price is not None:
                records.append({"code": code, "name": names[code], "price": price, "changePercent": finite_number(row.get("changePercent")), "marketTime": row.get("timestamp") or row.get("tradeTime"), "delayMinutes": finite_number(row.get("delayMinutes"))})
        if not records:
            raise ProviderError("CME official response contained no supported futures rows")
        return envelope(records, DataMeta.now("CME Group Market Data API", source_type="exchange-official-licensed-api", freshness="live-or-licensed-delay", schema_version="market.us-futures.official.v1"))


class SinaGlobalFuturesProvider:
    SYMBOLS = {"hf_ES": "标普500期货", "hf_NQ": "纳斯达克100期货", "hf_YM": "道琼斯期货"}

    def __init__(self, session=requests, timeout: int = 10):
        self.session, self.timeout = session, timeout

    def snapshot(self):
        response = self.session.get("https://hq.sinajs.cn/list=" + ",".join(self.SYMBOLS), headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = "gbk"
        records = []
        for symbol, raw in re.findall(r'var hq_str_(\w+)="([^"]*)"', response.text):
            fields = raw.split(",")
            price = finite_number(fields[0] if fields else None)
            if symbol in self.SYMBOLS and price is not None:
                records.append({"code": symbol, "name": self.SYMBOLS[symbol], "price": price, "changePercent": finite_number(fields[1] if len(fields) > 1 else None), "marketTime": fields[6] if len(fields) > 6 else None})
        if not records:
            raise ProviderError("Sina global futures response contained no valid rows")
        return envelope(records, DataMeta.now("sina-global-futures", source_type="commercial-public-interface", freshness="delayed-or-live", schema_version="market.us-futures.v1", note="公开商业源；不标记为CME官方结算数据"))
