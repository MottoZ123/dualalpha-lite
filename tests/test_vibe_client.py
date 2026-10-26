import unittest

from research_core.config import AppConfig
from research_core.vibe_client import VibeResearchClient


class Response:
    status_code = 200
    text = ""

    def json(self):
        return {"ok": True}


class Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response()


class VibeClientTests(unittest.TestCase):
    def config(self):
        return AppConfig(
            data_dir=None, reports_dir=None, vibe_base_url="http://127.0.0.1:8900",
            vibe_api_key="access", vibe_timeout_seconds=5, api_key="",
            allow_origins=(), consensus_threshold=0.53, enable_model_execution=False,
        )

    def test_authorization_and_code_validation(self):
        session = Session()
        client = VibeResearchClient(self.config(), session=session)
        self.assertEqual(client.quote(["600519"]), {"ok": True})
        self.assertEqual(session.calls[0][1]["headers"]["Authorization"], "Bearer access")
        with self.assertRaises(ValueError):
            client.quote(["bad"])


if __name__ == "__main__":
    unittest.main()
