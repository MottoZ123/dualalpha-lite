"""Read-only research tools shared by FastAPI, MCP, and future agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import AppConfig, get_app_config
from .schemas import compare_prediction_sets, normalize_predictions
from .vibe_client import VibeResearchClient


def _report_day(config: AppConfig, day: str | None = None, required_files: tuple[str, ...] = ()) -> Path:
    if day:
        if len(day) != 8 or not day.isdigit():
            raise ValueError("day 必须是 YYYYMMDD")
        target = config.reports_dir / day
        if not target.is_dir():
            raise FileNotFoundError(f"没有找到 {day} 的报告")
        missing = [name for name in required_files if not (target / name).is_file()]
        if missing:
            raise FileNotFoundError(f"{day} 归档不完整，缺少：{', '.join(missing)}")
        return target
    candidates = sorted((p for p in config.reports_dir.glob("[0-9]" * 8) if p.is_dir()), reverse=True)
    for candidate in candidates:
        if all((candidate / name).is_file() for name in required_files):
            return candidate
    wanted = "、".join(required_files) if required_files else "日期目录"
    raise FileNotFoundError(f"还没有包含 {wanted} 的完整 AB_Test_Reports 归档")


def load_predictions(engine: str, day: str | None = None, config: AppConfig | None = None) -> tuple[str, dict]:
    cfg = config or get_app_config()
    name = engine.strip().lower()
    if name not in {"tx", "bs"}:
        raise ValueError("engine 只能是 tx 或 bs")
    filename = f"{name}_raw_preds.json"
    folder = _report_day(cfg, day, (filename,))
    path = folder / filename
    if not path.is_file():
        raise FileNotFoundError(str(path))
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 的根节点不是对象")
    return folder.name, data


def latest_predictions(engine: str, day: str | None = None, config: AppConfig | None = None) -> dict:
    actual_day, raw = load_predictions(engine, day, config)
    return {"day": actual_day, "engine": engine.upper(), "records": normalize_predictions(raw, engine)}


def latest_comparison(day: str | None = None, config: AppConfig | None = None) -> dict:
    cfg = config or get_app_config()
    complete = _report_day(cfg, day, ("tx_raw_preds.json", "bs_raw_preds.json"))
    tx_day, tx = load_predictions("tx", complete.name, cfg)
    bs_day, bs = load_predictions("bs", tx_day, cfg)
    result = compare_prediction_sets(tx, bs, cfg.consensus_threshold)
    result["day"] = bs_day
    return result


def execute_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    args = arguments or {}
    if name == "latest_predictions":
        return latest_predictions(str(args.get("engine", "tx")), args.get("day"))
    if name == "compare_tx_bs":
        return latest_comparison(args.get("day"))
    vibe = VibeResearchClient()
    if name == "query_quote":
        return vibe.quote(list(args.get("codes") or []))
    if name == "query_valuation":
        return vibe.valuation(str(args.get("code", "")))
    if name == "query_reports":
        return vibe.reports(str(args.get("code", "")), int(args.get("pages", 2)))
    if name == "query_news":
        return vibe.news(str(args.get("code", "")), int(args.get("limit", 20)))
    if name == "query_financials":
        return vibe.financials(str(args.get("code", "")))
    raise ValueError(f"未知工具：{name}")


TOOL_DEFINITIONS = [
    {"name": "latest_predictions", "description": "读取已归档的 TX 或 BS 结构化预测", "inputSchema": {"type": "object", "properties": {"engine": {"type": "string", "enum": ["tx", "bs"]}, "day": {"type": "string"}}, "required": ["engine"]}},
    {"name": "compare_tx_bs", "description": "比较同一交易日 TX 与 BS 的概率、差值和共振状态", "inputSchema": {"type": "object", "properties": {"day": {"type": "string"}}}},
    {"name": "query_quote", "description": "通过本地 Vibe-Research 查询 A 股行情", "inputSchema": {"type": "object", "properties": {"codes": {"type": "array", "items": {"type": "string"}}}, "required": ["codes"]}},
    {"name": "query_valuation", "description": "通过本地 Vibe-Research 查询个股估值", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "query_reports", "description": "通过本地 Vibe-Research 查询个股研报", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "pages": {"type": "integer"}}, "required": ["code"]}},
    {"name": "query_news", "description": "通过本地 Vibe-Research 查询个股新闻", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["code"]}},
    {"name": "query_financials", "description": "通过本地 Vibe-Research 查询关键财务指标", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
]
