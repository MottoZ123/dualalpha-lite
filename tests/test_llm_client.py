import unittest

from research_core.config import ProviderConfig
from research_core.llm_client import LLMError, chat_completion_text


class Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        self.cfg = ProviderConfig("test", "secret", "model", "https://example.test/v1", 5, 1)

    def test_extracts_text_and_never_places_key_in_payload(self):
        session = Session([Response(payload={"choices": [{"message": {"content": "ok"}}]})])
        result = chat_completion_text(self.cfg, [{"role": "user", "content": "hello"}], session=session)
        self.assertEqual(result, "ok")
        self.assertNotIn("secret", str(session.calls[0][1]["json"]))

    def test_deepseek_v4_uses_explicit_thinking_format(self):
        cfg = ProviderConfig(
            "deepseek", "secret", "deepseek-v4-pro", "https://api.deepseek.com", 5, 1,
            thinking_mode="enabled", reasoning_effort="high",
        )
        session = Session([Response(payload={"choices": [{"message": {"content": "ok"}}]})])
        chat_completion_text(cfg, [{"role": "user", "content": "hello"}], session=session)
        payload = session.calls[0][1]["json"]
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "high")

    def test_non_retryable_400_raises(self):
        session = Session([Response(400, text="bad request")])
        with self.assertRaises(LLMError):
            chat_completion_text(self.cfg, [], session=session)

    def test_blank_content_is_not_accepted_as_success(self):
        session = Session([Response(payload={"choices": [{"message": {"content": ""}}]})])
        with self.assertRaises(LLMError):
            chat_completion_text(self.cfg, [{"role": "user", "content": "hello"}], session=session)


if __name__ == "__main__":
    unittest.main()
