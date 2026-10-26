import unittest
import json
import tempfile
from pathlib import Path

from workbench_core.config import load_workbench_config
from workbench_core.public_providers import CmeOfficialFuturesProvider, EastMoneyProvider, InstitutionalMacroProvider, OfficialExchangeLimitProvider, SinaGlobalFuturesProvider, SseInvestorAccountsProvider


class Response:
    def __init__(self, *, payload=None, text=""):
        self._payload, self.text, self.encoding = payload, text, "utf-8"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class LimitPoolSession:
    @staticmethod
    def get(url, **_kwargs):
        count = 42 if "ZTPool" in url else 7 if "DTPool" in url else 8
        return Response(payload={"data": {"tc": count, "qdate": 20260818, "pool": []}})


class InstitutionalSession:
    @staticmethod
    def get(url, **_kwargs):
        if "fredgraph" in url:
            code = url.rsplit("=", 1)[-1]
            return Response(text=f"DATE,{code}\n2026-08-14,.\n2026-08-17,4.25\n")
        currency = "CNY" if ".CNY." in url else "USD"
        value = "8.10" if currency == "CNY" else "1.20"
        return Response(text=f"TIME_PERIOD,OBS_VALUE\n2026-08-15,{value}\n")


class FuturesSession:
    @staticmethod
    def get(*_args, **_kwargs):
        return Response(text='var hq_str_hf_ES="6500.0,0.25,0,0,0,0,2026-08-17 16:00:00";\nvar hq_str_hf_NQ="24000.0,-0.1,0,0,0,0,2026-08-17 16:00:00";')


class SseSession:
    @staticmethod
    def get(*_args, **_kwargs):
        return Response(payload={"result": [
            {"TERM": "2026.06", "PERSON": "285.2384", "ORG": "1.2717", "A_PERSON": "285.1894", "A_ORG": "1.2700", "B_PERSON": ".0490", "B_ORG": ".0017", "MDATE": "202607"},
            {"TERM": "2026.07", "PERSON": "264.5000", "ORG": "1.0400", "A_PERSON": "264.4500", "A_ORG": "1.0300", "B_PERSON": ".0500", "B_ORG": ".0100", "MDATE": "202607"},
        ]})


class WorldBankSession:
    @staticmethod
    def get(*_args, **_kwargs):
        rows = [{"date": str(year), "value": float(year - 1990)} for year in range(2000, 2026)]
        return Response(payload=[{"page": 1}, list(reversed(rows))])


class CmeSession:
    @staticmethod
    def get(*_args, **_kwargs):
        return Response(payload={"quotes": [{"symbol": "ES", "last": 6500, "changePercent": .2, "timestamp": "2026-08-17T20:00:00Z"}]})


class FormalUpstreamTests(unittest.TestCase):
    def test_exact_limit_pool_counts_and_seal_rate(self):
        result = EastMoneyProvider(session=LimitPoolSession, min_interval=0).limit_pools("20260818")
        self.assertEqual(result["data"]["limitUp"], 42)
        self.assertEqual(result["data"]["brokenLimit"], 8)
        self.assertEqual(result["data"]["sealRate"], 84.0)
        self.assertEqual(result["meta"]["source_type"], "commercial-public-interface")

    def test_institutional_macro_and_ecb_cross_rate(self):
        provider = InstitutionalMacroProvider(session=InstitutionalSession)
        macro = provider.macro()
        self.assertEqual(len(macro["data"]), 5)
        self.assertEqual(macro["meta"]["source_type"], "official-public-data")
        fx = provider.fx()
        self.assertEqual(fx["data"][0]["pair"], "USD/CNY")
        self.assertAlmostEqual(fx["data"][0]["value"], 6.75)

    def test_sina_futures_is_explicitly_commercial(self):
        result = SinaGlobalFuturesProvider(session=FuturesSession).snapshot()
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["meta"]["source_type"], "commercial-public-interface")

    def test_fund_benchmark_comes_from_public_config(self):
        fund = next(item for item in load_workbench_config().universe if item.code == "161725")
        self.assertEqual(fund.benchmark_code, "H30539")
        self.assertIn("95%", fund.benchmark_formula)

    def test_sse_monthly_accounts_are_not_mislabeled_as_unique_investors(self):
        result = SseInvestorAccountsProvider(session=SseSession).snapshot()
        self.assertEqual(result["data"]["latest"]["month"], "2026.07")
        self.assertEqual(result["data"]["latest"]["newStockAccounts"], 265.54)
        self.assertIn("不是唯一投资者人数", result["data"]["definition"])
        self.assertEqual(result["meta"]["source_type"], "exchange-official-public-data")

    def test_world_bank_buffett_history_calculates_empirical_percentile(self):
        result = InstitutionalMacroProvider(session=WorldBankSession).buffett_history()
        self.assertEqual(result["data"]["latestYear"], "2025")
        self.assertEqual(result["data"]["historicalPercentile"], 100.0)
        self.assertEqual(result["data"]["observations"], 26)

    def test_official_limit_adapter_only_reads_explicit_snapshot_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sse.json"
            path.write_text(json.dumps({"rows": [
                {"lastPrice": 10, "upperLimit": 10, "lowerLimit": 8, "highPrice": 10},
                {"lastPrice": 9, "upperLimit": 10, "lowerLimit": 8, "highPrice": 10},
                {"lastPrice": 8, "upperLimit": 10, "lowerLimit": 8, "highPrice": 9},
            ]}), encoding="utf-8")
            result = OfficialExchangeLimitProvider((str(path),)).snapshot()
        self.assertEqual(result["data"]["limitUp"], 1)
        self.assertEqual(result["data"]["brokenLimit"], 1)
        self.assertEqual(result["data"]["limitDown"], 1)
        self.assertEqual(result["meta"]["source_type"], "exchange-official-licensed-feed")

    def test_cme_connector_requires_and_preserves_official_subscription(self):
        result = CmeOfficialFuturesProvider(session=CmeSession, endpoint="https://licensed.example/quotes", api_key="secret").snapshot()
        self.assertEqual(result["data"][0]["code"], "ES")
        self.assertEqual(result["meta"]["source_type"], "exchange-official-licensed-api")


if __name__ == "__main__":
    unittest.main()
