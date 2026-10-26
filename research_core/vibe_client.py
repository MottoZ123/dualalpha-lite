"""Adapter for a separately upgradeable local Vibe-Research backend."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from .config import AppConfig, get_app_config


class VibeResearchError(RuntimeError):
    pass


class VibeResearchClient:
    def __init__(self, config: AppConfig | None = None, session: Any = requests):
        self.config = config or get_app_config()
        self.session = session
        parsed = urlparse(self.config.vibe_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("VIBE_RESEARCH_BASE_URL 必须是有效的 http(s) 地址")

    def _get(self, path: str, **params: Any) -> Any:
        headers = {}
        if self.config.vibe_api_key:
            headers["Authorization"] = f"Bearer {self.config.vibe_api_key}"
        try:
            response = self.session.get(
                f"{self.config.vibe_base_url}{path}",
                params=params,
                headers=headers,
                timeout=self.config.vibe_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise VibeResearchError(f"Vibe-Research 不可用：{exc}") from exc
        if response.status_code >= 400:
            raise VibeResearchError(f"Vibe-Research HTTP {response.status_code}: {(response.text or '')[:300]}")
        try:
            return response.json()
        except ValueError as exc:
            raise VibeResearchError("Vibe-Research 返回了非 JSON 数据") from exc

    def health(self) -> dict:
        return self._get("/api/health")

    def quote(self, codes: list[str]) -> Any:
        cleaned = [str(code).strip() for code in codes]
        if not cleaned or any(len(code) != 6 or not code.isdigit() for code in cleaned):
            raise ValueError("codes 必须是非空的 6 位股票代码列表")
        return self._get("/api/quote", codes=",".join(cleaned))

    def valuation(self, code: str) -> Any:
        return self._get("/api/valuation", code=_code(code))

    def reports(self, code: str, pages: int = 2) -> Any:
        return self._get("/api/reports", code=_code(code), pages=max(1, min(int(pages), 5)))

    def news(self, code: str, limit: int = 20) -> Any:
        return self._get("/api/news", code=_code(code), limit=max(1, min(int(limit), 50)))

    def financials(self, code: str) -> Any:
        return self._get("/api/financials", code=_code(code))


def _code(code: str) -> str:
    value = str(code).strip()
    if len(value) != 6 or not value.isdigit():
        raise ValueError("股票代码必须是 6 位数字")
    return value
