from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class DataMeta:
    source: str
    source_type: str
    fetched_at: str
    market_time: str | None = None
    freshness: str = "live"
    quality: str = "normal"
    fallback: bool = False
    schema_version: str = "motto.v1"
    note: str | None = None

    @classmethod
    def now(cls, source: str, source_type: str = "public-interface", **changes: Any):
        return cls(source=source, source_type=source_type, fetched_at=datetime.now(timezone.utc).isoformat(), **changes)

    def public(self) -> dict[str, Any]:
        return asdict(self)


def envelope(data: Any, meta: DataMeta, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": meta.public(), "errors": errors or []}
