import threading
import time
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from motto_core.analytics import chart_indicators, comprehensive_top_observer, condition_matrix, macd, market_temperature, market_top_observer, rsi, technical_top_inputs, trend_assessment
from motto_core.cache import SWRCache
from motto_core.config import MottoConfig, ORIGINAL_UNIVERSE, load_motto_config
from motto_core.contracts import finite_number
from motto_core.providers import TencentMarketProvider
from motto_core.research_registry import ResearchRegistry
from motto_core.service import MottoService
from motto_core.state import SignalStateStore
from motto_core.market_clock import market_clock


class FakeResponse:
    text = 'v_sz300308="51~中际旭创~300308~100.00~98.00~99.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~20260817143500~2.00~2.04";'
    encoding = ""

    def raise_for_status(self):
        return None


class FakeSearchResponse(FakeResponse):
    text = 'v_hint="sz~300308~中际旭创~zhongjixuchuang~GP-A^sh~600519~贵州茅台~guizhoumaotai~GP-A^hk~03308~\\u4e2d\\u9645\\u65ed\\u521b~zhongjixuchuang~GP";'


class FakeSession:
    @staticmethod
    def get(url, *_args, **_kwargs):
        if "smartbox.gtimg.cn" in url:
            return FakeSearchResponse()
        return FakeResponse()


class MottoCoreTests(unittest.TestCase):
    def test_market_clock_handles_cn_trade_lunch_weekend_and_us_dst(self):
        trading = market_clock(datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc))
        lunch = market_clock(datetime(2026, 8, 17, 4, 0, tzinfo=timezone.utc))
        weekend = market_clock(datetime(2026, 8, 16, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(trading["cn"]["state"], "trading")
        self.assertEqual(trading["nextRefreshSeconds"], 5)
        self.assertEqual(lunch["cn"]["state"], "lunch")
        self.assertEqual(weekend["cn"]["state"], "closed")
        self.assertTrue(trading["us"]["dstAware"])
        self.assertEqual(trading["calendarConfidence"], "official-annual-2026")
        holiday = market_clock(datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(holiday["cn"]["state"], "closed")
        self.assertTrue(holiday["cn"]["holiday"])
        hk_holiday = market_clock(datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(hk_holiday["hk"]["state"], "closed")
        self.assertTrue(hk_holiday["hk"]["holiday"])
        us_holiday = market_clock(datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc))
        self.assertEqual(us_holiday["us"]["state"], "closed")
        self.assertTrue(us_holiday["us"]["holiday"])
        outside_coverage = market_clock(datetime(2027, 8, 17, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(outside_coverage["calendarConfidence"], "weekday-session-only")

    def test_a_mode_has_no_holdings_but_reserves_interface(self):
        service = MottoService(provider=TencentMarketProvider(session=FakeSession))
        caps = service.portfolio_capabilities()
        self.assertEqual(caps["mode"], "none")
        self.assertFalse(caps["enabled"])
        self.assertTrue(caps["interfaceReserved"])

    def test_original_universe_is_preserved(self):
        config = load_motto_config()
        expected = {item.code for item in ORIGINAL_UNIVERSE}
        actual = {item.code for item in config.universe}
        self.assertEqual(len(expected), 11)
        self.assertTrue(expected.issubset(actual))

    def test_non_finite_values_are_rejected(self):
        self.assertIsNone(finite_number(float("nan")))
        self.assertIsNone(finite_number(float("inf")))
        self.assertEqual(finite_number("1.25"), 1.25)

    def test_condition_matrix_reports_insufficient_data(self):
        result = condition_matrix(range(1, 30))
        self.assertEqual(result["m60"]["state"], "insufficient")
        self.assertEqual(result["dataQuality"], "partial")
        self.assertEqual(result["conclusion"]["label"], "数据不足")
        self.assertEqual(len(result["featureProfile"]), 6)
        self.assertIsNotNone(rsi(range(1, 30)))

    def test_condition_matrix_exposes_visual_features_and_direct_conclusion(self):
        closes = [100 + index * .4 for index in range(90)]
        volumes = [1000 + (index % 7) * 20 for index in range(90)]
        result = condition_matrix(closes, volumes)
        self.assertEqual(result["dataQuality"], "complete")
        self.assertIn(result["conclusion"]["label"], {"条件偏强", "中性观察", "条件偏弱"})
        self.assertTrue(all("score" in row and "display" in row for row in result["featureProfile"]))

    def test_top_observer_discloses_coverage(self):
        result = market_top_observer({"valuation": 100, "sentiment": None})
        self.assertEqual(result["coverage"], .3)
        self.assertEqual(result["conclusion"], "insufficient")

    def test_tencent_parser_preserves_identity_and_source(self):
        item = next(item for item in ORIGINAL_UNIVERSE if item.code == "300308")
        result = TencentMarketProvider(session=FakeSession).quotes([item])
        self.assertEqual(result["data"][0]["code"], "300308")
        self.assertEqual(result["data"][0]["price"], 100.0)
        self.assertEqual(result["meta"]["source"], "tencent-market")

    def test_personal_stock_search_resolves_code_or_name_without_creating_holdings(self):
        service = MottoService(provider=TencentMarketProvider(session=FakeSession))
        result = service.search_instruments("贵州茅台")
        matched = next(row for row in result["data"] if row["code"] == "600519")
        self.assertEqual(matched["name"], "贵州茅台")
        remote = TencentMarketProvider(session=FakeSession).search("中际旭创")
        self.assertEqual(next(row for row in remote["data"] if row["code"] == "03308")["name"], "中际旭创")
        self.assertEqual(service._instrument("600519").market, "CN")
        self.assertFalse(service.portfolio_capabilities()["enabled"])

    def test_single_flight_builds_once(self):
        cache = SWRCache()
        calls = []
        results = []
        barrier = threading.Barrier(4)

        def builder():
            calls.append(1)
            time.sleep(.04)
            return {"ok": True}

        def worker():
            barrier.wait()
            results.append(cache.get("same", builder, 60, 120, background=False)[0])

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 4)

    def test_disk_last_known_good_survives_new_cache_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SWRCache(directory)
            self.assertEqual(first.get("quotes", lambda: {"value": 7}, 60, 120, background=False)[0]["value"], 7)
            second = SWRCache(directory)
            self.assertEqual(second.peek("quotes").value["value"], 7)
            self.assertFalse(second.status("quotes", 120)["hardExpired"])

    def test_complete_dashboard_package_is_cached_and_exposed_to_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MottoService(cache=SWRCache(directory), provider=TencentMarketProvider(session=FakeSession))
            builds = []

            def build_dashboard():
                builds.append(1)
                return {"schemaVersion": "motto.dashboard.v3", "dataStatus": {"bundleFingerprint": "verified"}}

            service._build_dashboard = build_dashboard
            first = service.all()
            second = service.all()
            self.assertEqual(first["dataStatus"]["bundleFingerprint"], "verified")
            self.assertEqual(second["dataStatus"]["dashboardCacheState"], "fresh")
            self.assertEqual(len(builds), 1)
            self.assertEqual(service.ready()["critical"]["dashboard"], "ready")

    def test_partial_flow_rows_do_not_break_market_package(self):
        service = MottoService(config=MottoConfig(universe=()), provider=TencentMarketProvider(session=FakeSession))
        service.fund_flows = lambda _kind="industry": {"data": [{"mainNetInflow": None}, {"mainNetInflow": 10.0}], "meta": {"source": "fixture"}}
        service.market_snapshot = lambda: {"data": {"advancingRatio": 50.0}}
        service.valuations = lambda _codes=None: {"data": []}
        service.margin = lambda: {"data": {}}
        result = service._market_analysis([])
        self.assertEqual(result["sixDimensions"][-1]["value"], 100.0)

    def test_cross_market_alignment_uses_strictly_prior_us_close(self):
        cn = [("2026-08-17", .01), ("2026-08-18", -.02)]
        us = [("2026-08-14", .03), ("2026-08-17", -.01), ("2026-08-18", .5)]
        paired = MottoService._pair_prior_market(cn, us)
        self.assertEqual(paired[0][2], "2026-08-14")
        self.assertEqual(paired[1][2], "2026-08-17")
        self.assertNotEqual(paired[1][2], "2026-08-18")

    def test_signal_state_first_load_is_silent_then_reports_flip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SignalStateStore(Path(directory) / ".dash_state.json")
            self.assertEqual(store.compare_and_store({"x": {"state": "above", "asOf": "d1", "source": "test"}}), [])
            changes = store.compare_and_store({"x": {"state": "below", "asOf": "d2", "source": "test"}})
            self.assertEqual(changes[0]["from"], "above")
            self.assertEqual(changes[0]["to"], "below")

    def test_chart_indicators_and_trend_are_derived(self):
        rows = [{"close": float(index), "volume": float(index)} for index in range(1, 90)]
        indicators = chart_indicators(rows)
        self.assertEqual(len(indicators["ma60"]), 89)
        self.assertEqual(len(indicators["macd"]["histogram"]), 89)
        self.assertEqual(trend_assessment([row["close"] for row in rows])["state"], "上涨")
        self.assertIn(macd([1, 2, 3, 4])["state"], {"golden", "dead", "above", "below"})

    def test_market_temperature_uses_pdf_weights(self):
        result = market_temperature([1, 2, -1, 0], [2, 2])
        self.assertAlmostEqual(result["components"]["sectorBreadth"], .25)
        self.assertAlmostEqual(result["raw"], .55)
        self.assertEqual(result["score"], 77.5)
        self.assertEqual(result["state"], "普涨")

    def test_complete_top_model_discloses_manual_and_automatic_gaps(self):
        result = comprehensive_top_observer({
            "broadPePercentile": 80, "rsiHeat": 75, "maBiasPercentile": 70,
            "macdDivergenceHeat": 85, "volumePriceDivergenceHeat": 25,
            "advancingRatio": 72, "aboveM60Ratio": 76, "realizedVolatilityPercentile": 30,
        })
        self.assertEqual(result["model"], "pdf-five-dimension.v1")
        self.assertEqual(result["dimensionDetails"]["valuation"]["manualDone"], 0)
        self.assertIn("巴菲特指标分位", result["dimensionDetails"]["valuation"]["missing"])
        self.assertGreater(result["coverage"], .5)

    def test_technical_top_inputs_use_historical_percentiles(self):
        rows = [{"close": 100 + index * .3 + (index % 7) * .1, "volume": 1000 + index * 10} for index in range(180)]
        result = technical_top_inputs(rows)
        self.assertIsNotNone(result["maBiasPercentile"])
        self.assertIsNotNone(result["realizedVolatilityPercentile"])

    def test_model_promotion_hashes_artifacts_and_rollback_changes_active_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = ResearchRegistry(root / "registry.sqlite3")
            releases = []
            for index in (1, 2):
                artifact = root / f"job-{index}" / "tx" / "models_tx_v7"
                artifact.mkdir(parents=True)
                (artifact / "model.bin").write_bytes(f"model-{index}".encode())
                releases.append(registry.promote("tx", {"id": f"job-{index}", "mode": "training", "status": "completed", "output_dir": str(root / f"job-{index}"), "results": {"tx": {"dataVersion": f"data-{index}"}}}))
            self.assertEqual(len(releases[-1]["artifact_sha256"]), 64)
            self.assertEqual(registry.active_release("tx")["job_id"], "job-2")
            registry.rollback("tx")
            self.assertEqual(registry.active_release("tx")["job_id"], "job-1")


if __name__ == "__main__":
    unittest.main()
