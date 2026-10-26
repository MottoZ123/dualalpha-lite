from __future__ import annotations

import hashlib
import json
import re
import threading
from bisect import bisect_left
from datetime import datetime, timezone
from statistics import fmean

from .analytics import chart_indicators, comprehensive_top_observer, condition_matrix, market_temperature, six_dimension_signals, technical_top_inputs, trend_assessment
from .cache import SWRCache
from .config import ROOT, Instrument, load_workbench_config
from .contracts import DataMeta, envelope
from .providers import TencentMarketProvider
from .public_providers import CmeOfficialFuturesProvider, DanjuanValuationProvider, EastMoneyFundProvider, EastMoneyProvider, InstitutionalMacroProvider, OfficialExchangeLimitProvider, SinaGlobalFuturesProvider, SseInvestorAccountsProvider
from .state import SignalStateStore
from .market_clock import market_clock


class WorkbenchService:
    QUOTE_HARD_TTL = 300
    ANALYSIS_HARD_TTL = 1800
    DASHBOARD_HARD_TTL = 1800
    QUOTE_KEY = "quotes:v3"
    ANALYSIS_KEY = "market-analysis:v3"
    DASHBOARD_KEY = "dashboard:v3"

    def __init__(self, config=None, provider=None, cache=None, eastmoney=None, danjuan=None, funds=None, macro=None, futures=None, investor_accounts=None, official_limits=None, cme=None):
        self.config = config or load_workbench_config()
        self.provider = provider or TencentMarketProvider()
        self.eastmoney = eastmoney or EastMoneyProvider()
        self.danjuan = danjuan or DanjuanValuationProvider()
        self.funds = funds or EastMoneyFundProvider()
        self.macro_provider = macro or InstitutionalMacroProvider()
        self.futures_provider = futures or SinaGlobalFuturesProvider()
        self.investor_accounts_provider = investor_accounts or SseInvestorAccountsProvider()
        self.official_limits_provider = official_limits or OfficialExchangeLimitProvider()
        self.cme_provider = cme or CmeOfficialFuturesProvider()
        self.cache = cache or SWRCache(ROOT / ".motto-cache")
        self.signal_store = SignalStateStore(ROOT / ".dash_state.json")
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._warm_started = False

    def prewarm(self):
        if self._warm_started:
            return
        self._warm_started = True
        threading.Thread(target=self._safe_prewarm, name="motto-prewarm", daemon=True).start()

    def _safe_prewarm(self):
        try:
            self.cache.get(self.DASHBOARD_KEY, self._build_dashboard, self._dashboard_ttl(), self.DASHBOARD_HARD_TTL, background=False)
        except Exception:
            pass

    def _dashboard_ttl(self):
        clock = market_clock()
        if clock["cn"]["state"] == "trading":
            return min(30, self.config.refresh_seconds["market"])
        if clock["cn"]["state"] == "lunch":
            return min(90, self.config.refresh_seconds["market"])
        return min(300, self.config.refresh_seconds["market"])

    def _quote_package(self):
        return self.provider.quotes(self.config.universe)

    def realtime(self):
        clock = market_clock()
        ttl = min(self.config.refresh_seconds["quote"], clock["nextRefreshSeconds"])
        value, state = self.cache.get(self.QUOTE_KEY, self._quote_package, ttl, self.QUOTE_HARD_TTL)
        return {**value, "cacheState": state}

    def market_snapshot(self):
        clock = market_clock()
        ttl = 15 if clock["cn"]["state"] == "trading" else 60 if clock["cn"]["state"] == "lunch" else 300
        try:
            value, state = self.cache.get("market-breadth:v2", self.eastmoney.market_breadth, ttl, 1800)
            official = self.limit_pools(prefer_official=True)
            if isinstance(official.get("data"), dict) and official["meta"].get("source_type") == "exchange-official-licensed-feed":
                value = {**value, "data": {**value["data"], **official["data"], "preciseCommercialPoolAvailable": False, "officialLimitPoolAvailable": True, "limitMethod": "licensed-exchange-feed"}}
            return {**value, "cacheState": state}
        except Exception as exc:
            result = self._unavailable("eastmoney-market-breadth", str(exc)[:220])
            result["data"] = {"total": None, "up": None, "down": None, "flat": None, "advancingRatio": None, "limitUpEstimate": None, "limitDownEstimate": None, "brokenLimit": None, "sealRate": None}
            return result

    def realtime_patch(self):
        quotes = self.realtime()
        breadth = self.market_snapshot()
        flow = self.fund_flows("industry")
        return {
            "schemaVersion": "motto.realtime-patch.v1", "data": quotes.get("data", []),
            "meta": quotes.get("meta"), "cacheState": quotes.get("cacheState"),
            "marketStats": breadth, "industryFlow": flow,
            "clock": market_clock(),
        }

    @staticmethod
    def _unavailable(source: str, note: str):
        return envelope([], DataMeta.now(source, freshness="unavailable", quality="unavailable", fallback=True, note=note), [{"code": "upstream_unavailable", "message": note}])

    def fund_flows(self, kind="industry"):
        key = f"fund-flow:{kind}"
        try:
            value, state = self.cache.get(key, lambda: self.eastmoney.fund_flows(kind), self.config.refresh_seconds["fund_flow"], 3600)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("eastmoney-fund-flow", str(exc)[:220])

    def news(self, limit=30):
        try:
            value, state = self.cache.get("news", lambda: self.eastmoney.news(limit), self.config.refresh_seconds["news"], 1800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("eastmoney-news", str(exc)[:220])

    def margin(self):
        try:
            value, state = self.cache.get("margin:v2", self.eastmoney.margin_balance, 3600, 172800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("eastmoney-margin", str(exc)[:220])

    def valuations(self, codes=None):
        target_codes = codes or [item.code for item in self.config.universe if item.asset_type == "index"]
        records, errors = [], []
        for code in target_codes[:12]:
            provider_code = code if code.startswith(("SH", "SZ")) else f"SZ{code}" if code.startswith("399") else f"SH{code}"
            try:
                value, state = self.cache.get(f"valuation:{provider_code}", lambda code=provider_code: self.danjuan.valuation(code), self.config.refresh_seconds["valuation"], 86400)
                records.append({**value["data"], "requestedCode": code, "meta": value["meta"], "cacheState": state})
            except Exception as exc:
                errors.append({"code": code, "message": str(exc)[:180]})
        states = {}
        for row in records:
            percentile = row["percentile"]
            band = "high" if percentile >= 70 else "elevated" if percentile >= 55 else "low" if percentile <= 30 else "below" if percentile <= 45 else "normal"
            row["band"] = band
            states[f"{row['requestedCode']}:valuation"] = {"state": band, "asOf": row.get("date"), "source": row["meta"].get("source")}
        changes = self.signal_store.compare_and_store(states) if states else []
        meta = DataMeta.now("danjuan-index-valuation", freshness="mixed" if records and errors else "hourly" if records else "unavailable", quality="partial" if errors else "normal", fallback=bool(errors), note="无原子 PE-TTM 与历史分位时不生成估值结论")
        result = envelope(records, meta, errors)
        result.update({"alerts": {"high": [row for row in records if row["band"] == "high"], "low": [row for row in records if row["band"] == "low"]}, "changes": changes})
        return result

    def fund_snapshot(self, code: str):
        value, state = self.cache.get(f"fund:{code}", lambda: self.funds.snapshot(code), self.config.refresh_seconds.get("fund", 300), 172800)
        instrument = next((item for item in self.config.universe if item.code == code and item.asset_type == "fund"), None)
        benchmark = None
        if instrument and instrument.benchmark_code:
            benchmark = {
                "code": instrument.benchmark_code, "name": instrument.benchmark_name,
                "formula": instrument.benchmark_formula, "sourceUrl": instrument.benchmark_source_url,
                "sourceType": "fund-manager-official-disclosure", "proxyStatus": "metadata-only",
                "note": "已核验官方基准定义；同交易时点代理只用于观察，不驱动官方结算。",
            }
        benchmark_quote = None
        if instrument and instrument.benchmark_code in {"H30539", "399997"}:
            try:
                benchmark_item = Instrument("399997", "中证白酒", "CN", "index")
                quote_package = self.provider.quotes([benchmark_item])
                quote = quote_package["data"][0]
                benchmark_quote = {**quote, "officialIdentityCode": "399997", "legacyCode": "H30539", "identitySource": "CSI official factsheet", "quoteSource": quote_package["meta"].get("source"), "proxyChangePercent": round(quote["changePercent"] * .95, 4) if isinstance(quote.get("changePercent"), (int, float)) else None, "method": "中证白酒当日涨跌×95%；现金5%盘中贡献按0处理", "settlementEligible": False}
            except Exception:
                benchmark_quote = None
        mode = "fund-estimate" if value["data"].get("estimateChangePercent") is not None else "benchmark-intraday-proxy" if benchmark_quote else "official-nav-with-benchmark-metadata"
        return {**value, "data": {**value["data"], "benchmark": benchmark, "benchmarkQuote": benchmark_quote, "valuationMode": mode}, "cacheState": state}

    def limit_pools(self, prefer_official: bool = True):
        if prefer_official:
            try:
                value, state = self.cache.get("limit-pools:official:v1", self.official_limits_provider.snapshot, 15, 1800)
                return {**value, "cacheState": state, "officialStatus": "connected"}
            except Exception as exc:
                official_error = str(exc)[:220]
        else:
            official_error = "official feed not requested"
        try:
            value, state = self.cache.get("limit-pools:v1", self.eastmoney.limit_pools, 15 if market_clock()["cn"]["state"] == "trading" else 300, 1800)
            return {**value, "cacheState": state, "officialStatus": "authorization-required", "officialError": official_error}
        except Exception as exc:
            return self._unavailable("eastmoney-limit-pools", str(exc)[:220])

    def macro_snapshot(self):
        try:
            value, state = self.cache.get("macro:v1", self.macro_provider.macro, 3600, 172800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("institutional-macro", str(exc)[:220])

    def fx_snapshot(self):
        try:
            value, state = self.cache.get("fx:v1", self.macro_provider.fx, 3600, 172800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("ECB Data API", str(exc)[:220])

    def buffett_history(self):
        try:
            value, state = self.cache.get("buffett-history:v1", self.macro_provider.buffett_history, 86400, 604800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("World Bank WDI / WFE", str(exc)[:220])

    def investor_accounts(self):
        try:
            value, state = self.cache.get("investor-accounts:v2", self.investor_accounts_provider.snapshot, 86400, 604800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("Shanghai Stock Exchange monthly statistics", str(exc)[:220])

    def us_futures(self):
        try:
            value, state = self.cache.get("us-futures:cme:v1", self.cme_provider.snapshot, 15, 1800)
            return {**value, "data": [{**row, "sourceClass": "CME官方授权"} for row in value["data"]], "cacheState": state, "officialStatus": "connected"}
        except Exception as exc:
            official_error = str(exc)[:220]
        try:
            value, state = self.cache.get("us-futures:v1", self.futures_provider.snapshot, 15 if market_clock()["us"]["state"] == "trading" else 300, 1800)
            return {**value, "data": [{**row, "sourceClass": "新浪商业公开 · CME待授权"} for row in value["data"]], "cacheState": state, "officialStatus": "authorization-required", "officialError": official_error}
        except Exception as exc:
            return self._unavailable("sina-global-futures", str(exc)[:220])

    @staticmethod
    def _returns(rows, date_key="date", value_key="value"):
        result = []
        for previous, current in zip(rows, rows[1:]):
            before, after = previous.get(value_key), current.get(value_key)
            if isinstance(before, (int, float)) and isinstance(after, (int, float)) and before:
                result.append((str(current.get(date_key)), after / before - 1))
        return result

    @staticmethod
    def _pair_prior_market(cn_returns, us_returns):
        us_dates = [row[0] for row in us_returns]
        paired = []
        for cn_date, cn_value in cn_returns:
            index = bisect_left(us_dates, cn_date) - 1
            if index >= 0:
                paired.append((cn_date, cn_value, us_dates[index], us_returns[index][1]))
        return paired

    @staticmethod
    def _relationship(paired):
        if len(paired) < 30:
            return None
        x = [row[3] for row in paired]
        y = [row[1] for row in paired]
        mx, my = fmean(x), fmean(y)
        covariance = sum((a - mx) * (b - my) for a, b in zip(x, y))
        x_variance = sum((a - mx) ** 2 for a in x)
        y_variance = sum((b - my) ** 2 for b in y)
        correlation = covariance / (x_variance * y_variance) ** .5 if x_variance and y_variance else None
        beta = covariance / x_variance if x_variance else None
        latest = paired[-1]
        return {"samples": len(paired), "correlation": round(correlation, 4) if correlation is not None else None, "beta": round(beta, 4) if beta is not None else None, "latestUsDate": latest[2], "latestUsReturn": round(latest[3] * 100, 4), "latestCnDate": latest[0], "latestCnReturn": round(latest[1] * 100, 4), "conditionalMove": round(beta * latest[3] * 100, 4) if beta is not None else None}

    def _build_cross_market_impact(self):
        cn_items = [Instrument("000300", "沪深300", "CN", "index"), Instrument("399006", "创业板指", "CN", "index"), Instrument("000001", "上证指数", "CN", "index")]
        us_series = [("SP500", "标普500"), ("NASDAQCOM", "纳斯达克综合"), ("DJIA", "道琼斯工业")]
        cn_data = {}
        for item in cn_items:
            rows = self.provider.kline(item, "day", 500)["data"]
            cn_data[item.code] = self._returns(rows, value_key="close")
        records, errors = [], []
        for us_code, us_name in us_series:
            try:
                us_returns = self._returns(self.macro_provider.fred_series(us_code))
                for item in cn_items:
                    paired = self._pair_prior_market(cn_data[item.code], us_returns)
                    relation = self._relationship(paired[-250:])
                    if relation:
                        records.append({"usCode": us_code, "usName": us_name, "cnCode": item.code, "cnName": item.name, **relation})
            except Exception as exc:
                errors.append({"code": us_code, "message": str(exc)[:180]})
        if not records:
            raise RuntimeError("No cross-market pair has at least 30 aligned observations")
        meta = DataMeta.now("FRED US indices + Tencent CN indices", source_type="mixed-official-and-commercial-public-data", freshness="daily", quality="partial" if errors else "normal", fallback=False, schema_version="market.cross-impact.v1", note="中国交易日仅匹配严格早于其日期的最近美国收盘；相关性和beta描述条件关系，不代表因果")
        return envelope(records, meta, errors)

    def cross_market_impact(self):
        try:
            value, state = self.cache.get("cross-impact:v1", self._build_cross_market_impact, 3600, 172800)
            return {**value, "cacheState": state}
        except Exception as exc:
            return self._unavailable("cross-market-impact", str(exc)[:220])

    def _market_analysis(self, quotes):
        index_items = [item for item in self.config.universe if item.asset_type == "index"][:9]
        technical, trend_rows, top_inputs, errors = [], [], [], []
        for item in index_items:
            try:
                package = self.kline(item.code, "day", 160)
                rows = package["data"]
                condition = condition_matrix([row["close"] for row in rows], [row["volume"] for row in rows])
                technical.append({"code": item.code, "name": item.name, "conditions": condition, "meta": package["meta"]})
                trend_rows.append(trend_assessment([row["close"] for row in rows]))
                top_inputs.append({"code": item.code, **technical_top_inputs(rows)})
            except Exception as exc:
                errors.append({"code": item.code, "message": str(exc)[:160]})
        index_pct = [row.get("changePercent") for row in quotes if row.get("assetType") == "index" and isinstance(row.get("changePercent"), (int, float))]
        flow_package = self.fund_flows("industry")
        flow_rows = flow_package.get("data") if isinstance(flow_package.get("data"), list) else []
        sector_pct = [row.get("changePercent") for row in flow_rows if isinstance(row.get("changePercent"), (int, float))]
        temperature = market_temperature(sector_pct, index_pct)
        market_stats = self.market_snapshot()
        breadth_data = market_stats.get("data") if isinstance(market_stats.get("data"), dict) else {}
        advancing_ratio = breadth_data.get("advancingRatio")
        valuation_package = self.valuations(["000300", "000905", "000852"])
        valuation_values = [row["percentile"] for row in valuation_package["data"]]
        valuation = round(fmean(valuation_values), 2) if valuation_values else None
        margin_package = self.margin()
        margin_data = margin_package.get("data") if isinstance(margin_package.get("data"), dict) else {}
        margin_balance = margin_data.get("balance") if isinstance(margin_data, dict) else None
        margin_trillion = margin_balance / 1e12 if isinstance(margin_balance, (int, float)) else None
        margin_heat = max(0.0, min(100.0, (margin_trillion - 1.2) / 1.4 * 100)) if margin_trillion is not None else None
        mean_input = lambda key: round(fmean(row[key] for row in top_inputs if isinstance(row.get(key), (int, float))), 2) if any(isinstance(row.get(key), (int, float)) for row in top_inputs) else None
        rsi_heat = mean_input("rsi")
        ma_bias = mean_input("maBiasPercentile")
        macd_divergence = mean_input("macdDivergence")
        volume_divergence = mean_input("volumePriceDivergence")
        realized_volatility = mean_input("realizedVolatilityPercentile")
        above_m60 = mean_input("aboveM60")
        shanghai_volume = next((row.get("volumePercentile") for row in top_inputs if row["code"] == "000001"), None)
        buffett_package = self.buffett_history()
        buffett_data = buffett_package.get("data") if isinstance(buffett_package.get("data"), dict) else {}
        investor_package = self.investor_accounts()
        investor_data = investor_package.get("data") if isinstance(investor_package.get("data"), dict) else {}
        investor_latest = investor_data.get("latest") if isinstance(investor_data.get("latest"), dict) else {}
        model_inputs = {
            "broadPePercentile": valuation, "growthDividendPercentile": None, "buffettIndicatorPercentile": buffett_data.get("historicalPercentile"),
            "chinextTurnoverPercentile": None, "shanghaiVolumePercentile": shanghai_volume, "marginHeat": margin_heat, "retailAccountsPercentile": investor_latest.get("historicalPercentile"),
            "rsiHeat": rsi_heat, "maBiasPercentile": ma_bias, "macdDivergenceHeat": macd_divergence, "volumePriceDivergenceHeat": volume_divergence,
            "advancingRatio": advancing_ratio, "aboveM60Ratio": above_m60, "realizedVolatilityPercentile": realized_volatility,
        }
        model_sources = {
            "broadPePercentile": "danjuan-index-valuation", "buffettIndicatorPercentile": "World Bank WDI / WFE annual", "shanghaiVolumePercentile": "tencent-kline-volume-proxy", "marginHeat": "eastmoney-margin-daily", "retailAccountsPercentile": "SSE official monthly new stock accounts",
            "rsiHeat": "tencent-kline", "maBiasPercentile": "tencent-kline", "macdDivergenceHeat": "tencent-kline", "volumePriceDivergenceHeat": "tencent-kline",
            "advancingRatio": "eastmoney-a-share-atomic-quotes", "aboveM60Ratio": "tencent-index-anchors", "realizedVolatilityPercentile": "tencent-kline",
        }
        top = comprehensive_top_observer(model_inputs, model_sources)
        trend_scores = [row["score"] for row in trend_rows if row["score"] is not None]
        trend = {"score": round(fmean(trend_scores), 2), "state": "上涨" if fmean(trend_scores) > 35 else "下降" if fmean(trend_scores) < -35 else "震荡", "timeframe": "中期日线", "members": trend_rows} if trend_scores else {"score": None, "state": "数据不足", "timeframe": "中期日线", "members": trend_rows}
        finite_flows = [row.get("mainNetInflow") for row in flow_rows if isinstance(row.get("mainNetInflow"), (int, float))]
        fund_flow_heat = round(sum(value > 0 for value in finite_flows) / len(finite_flows) * 100, 2) if finite_flows else None
        dimensions = top["dimensions"]
        return {"breadth": advancing_ratio, "marketStats": market_stats, "temperature": temperature, "technical": technical, "trend": trend, "topObserver": top, "sixDimensions": six_dimension_signals(valuation=dimensions.get("valuation"), sentiment=dimensions.get("sentiment"), momentum=dimensions.get("momentum"), breadth=dimensions.get("breadth"), volatility=dimensions.get("volatility"), fund_flow=fund_flow_heat), "valuation": valuation_package, "margin": margin_package, "flow": {"coverage": len(flow_rows), "source": flow_package.get("meta")}, "errors": errors}

    def _build_dashboard(self):
        quotes = self.realtime()
        analysis_key = self.ANALYSIS_KEY
        analysis, analysis_state = self.cache.get(analysis_key, lambda: self._market_analysis(quotes["data"]), self.config.refresh_seconds["market"], self.ANALYSIS_HARD_TTL)
        original = [item for item in quotes["data"] if item.get("original")]
        indices = [item for item in quotes["data"] if item.get("assetType") == "index"]
        result = {
            "schemaVersion": "motto.dashboard.v3",
            "system": {"name": self.config.name, "portfolioMode": self.config.portfolio_mode, "timezone": self.config.timezone},
            "market": {"indices": indices, **analysis},
            "watchlist": original, "universe": quotes["data"],
            "portfolio": {"enabled": False, "mode": "none", "items": []},
            "extensions": {"vibe": {"enabled": self.config.vibe_enabled, "mode": self.config.vibe_mode}, "dualTrack": {"enabled": True, "frequency": "daily"}},
            "reference": {"macro": self.macro_snapshot(), "fx": self.fx_snapshot(), "usFutures": self.us_futures(), "investorAccounts": self.investor_accounts(), "buffettHistory": self.buffett_history(), "crossMarketImpact": self.cross_market_impact()},
            "dataStatus": {"quotes": quotes["meta"], "cacheState": quotes["cacheState"], "analysisCacheState": analysis_state, "clock": market_clock()},
        }
        fingerprint_source = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        result["dataStatus"]["bundleFingerprint"] = hashlib.sha256(fingerprint_source).hexdigest()[:20]
        result["dataStatus"]["builtAt"] = datetime.now(timezone.utc).isoformat()
        return result

    def all(self):
        value, state = self.cache.get(self.DASHBOARD_KEY, self._build_dashboard, self._dashboard_ttl(), self.DASHBOARD_HARD_TTL)
        return {**value, "dataStatus": {**value.get("dataStatus", {}), "dashboardCacheState": state}}

    def health(self):
        return {"ok": True, "service": "motto-stock-analysis", "startedAt": self.started_at}

    def ready(self):
        quote_status = self.cache.status(self.QUOTE_KEY, self.QUOTE_HARD_TTL)
        analysis_status = self.cache.status(self.ANALYSIS_KEY, self.ANALYSIS_HARD_TTL)
        dashboard_status = self.cache.status(self.DASHBOARD_KEY, self.DASHBOARD_HARD_TTL)
        quote_ready = quote_status["present"] and not quote_status["hardExpired"]
        analysis_ready = analysis_status["present"] and not analysis_status["hardExpired"]
        dashboard_ready = dashboard_status["present"] and not dashboard_status["hardExpired"]
        state = lambda status, available: "ready" if available else "hard-expired" if status["present"] else "cold"
        return {"ready": quote_ready and analysis_ready and dashboard_ready, "critical": {"quotes": state(quote_status, quote_ready), "analysis": state(analysis_status, analysis_ready), "dashboard": state(dashboard_status, dashboard_ready)}, "cache": {"quotes": quote_status, "analysis": analysis_status, "dashboard": dashboard_status}}

    def portfolio_capabilities(self):
        return {"mode": self.config.portfolio_mode, "enabled": False, "interfaceReserved": self.config.portfolio_interface_enabled, "supportedModes": ["none", "basic", "fund_lookthrough"], "requiresUserConfirmedPrivateData": True}

    def upstream_capabilities(self):
        return {
            "exchangeLimitFeed": {"configured": bool(self.official_limits_provider.paths), "sourceType": "exchange-official-licensed-feed", "fallback": "eastmoney-commercial-public-pool"},
            "cmeMarketData": {"configured": bool(self.cme_provider.endpoint and self.cme_provider.api_key), "sourceType": "exchange-official-licensed-api", "fallback": "sina-commercial-public-interface"},
            "sseInvestorAccounts": {"configured": True, "sourceType": "exchange-official-public-data"},
            "buffettHistory": {"configured": True, "sourceType": "official-public-data"},
            "h30539Proxy": {"configured": True, "identityCode": "399997", "legacyCode": "H30539", "settlementEligible": False},
            "crossMarketImpact": {"configured": True, "causal": False, "alignment": "strict-prior-US-close-to-next-CN-session"},
        }

    def _instrument(self, code: str):
        value = str(code).strip().upper()
        item = next((candidate for candidate in self.config.universe if candidate.code == value), None)
        if item:
            return item
        if re.fullmatch(r"\d{6}", value):
            return Instrument(value, value, "CN", "equity")
        if re.fullmatch(r"\d{5}", value):
            return Instrument(value, value, "HK", "equity")
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", value):
            return Instrument(value, value, "US", "equity")
        raise ValueError("instrument code must be a valid A-share, Hong Kong, or US symbol")

    def search_instruments(self, query: str, limit: int = 8):
        needle = str(query).strip()
        if not needle:
            return {"schemaVersion": "motto.instrument-search.v1", "data": [], "meta": {"source": "local-universe"}}
        folded = needle.casefold()
        local = [
            {"code": item.code, "name": item.name, "market": item.market, "assetType": item.asset_type}
            for item in self.config.universe
            if folded in item.code.casefold() or folded in item.name.casefold()
        ]
        merged = {row["code"]: row for row in local}
        source = "local-universe"
        note = None
        try:
            remote = self.provider.search(needle, limit)
            for row in remote.get("data", []):
                merged.setdefault(row["code"], row)
            source = remote.get("meta", {}).get("source") or "tencent-symbol-search"
        except Exception as exc:
            note = str(exc)[:180]
            if not merged and re.fullmatch(r"\d{5,6}|[A-Za-z][A-Za-z0-9.\-]{0,9}", needle):
                item = self._instrument(needle)
                try:
                    quote = self.provider.quotes([item]).get("data", [])[0]
                    merged[item.code] = {key: quote.get(key) for key in ("code", "name", "market", "assetType", "price", "changePercent")}
                    source = "tencent-market"
                except Exception:
                    merged[item.code] = {"code": item.code, "name": item.code, "market": item.market, "assetType": item.asset_type}
        return {
            "schemaVersion": "motto.instrument-search.v1",
            "data": list(merged.values())[:max(1, min(int(limit), 20))],
            "meta": {"source": source, "note": note},
        }

    def kline(self, code: str, period: str = "day", limit: int = 120):
        item = self._instrument(code)
        key = f"kline:{item.market}:{item.code}:{period}:{limit}"
        value, state = self.cache.get(key, lambda: self.provider.kline(item, period, limit), self.config.refresh_seconds["kline"], 86400)
        rows = value.get("data", [])
        return {**value, "indicators": chart_indicators(rows) if rows else {}, "cacheState": state}

    def intraday(self, code: str):
        item = self._instrument(code)
        key = f"intraday:{item.market}:{item.code}"
        value, state = self.cache.get(key, lambda: self.provider.intraday(item), self.config.refresh_seconds["intraday"], 900)
        rows = value.get("data", [])
        prices = [row.get("price") for row in rows if row.get("price") is not None]
        running, average = 0.0, []
        for index, price in enumerate(prices, 1):
            running += price
            average.append(round(running / index, 6))
        return {**value, "average": average, "cacheState": state}

    def technical(self, code: str):
        package = self.kline(code, "day", 160)
        rows = package["data"]
        conditions = condition_matrix([row["close"] for row in rows], [row["volume"] for row in rows])
        as_of = package["meta"].get("market_time")
        states = {
            f"{code}:m60": {"state": conditions["m60"]["state"], "asOf": as_of, "source": package["meta"].get("source")},
            f"{code}:macd": {"state": conditions["macd"]["state"], "asOf": as_of, "source": package["meta"].get("source")},
            f"{code}:rsi": {"state": conditions["rsi"]["state"], "asOf": as_of, "source": package["meta"].get("source")},
        }
        return {"code": code, "conditions": conditions, "trend": trend_assessment([row["close"] for row in rows]), "changes": self.signal_store.compare_and_store(states), "meta": package["meta"]}
