"""FastAPI facade for the existing TX/BS engines and local Vibe-Research data."""

from __future__ import annotations

import threading
import uuid
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from research_core.config import get_app_config, get_provider_config, public_config_status
from research_core.llm_client import LLMError, chat_completion_text
from research_core.schemas import compare_prediction_sets, normalize_predictions
from research_core.tools import latest_comparison, latest_predictions
from research_core.vibe_client import VibeResearchClient
from workbench_core import WorkbenchService
from workbench_core.analytics import condition_matrix
from workbench_core.research_registry import ResearchRegistry
from workbench_core.http_cache import etag_response


cfg = get_app_config()
app = FastAPI(title="Quant Research + Vibe API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cfg.allow_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(GZipMiddleware, minimum_size=800)
_RUN_LOCK = threading.Lock()
_TRAIN_LOCK = threading.Lock()
_BACKTEST_LOCK = threading.Lock()
_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_WORKBENCH = WorkbenchService()
_WORKBENCH.prewarm()
_REGISTRY = ResearchRegistry(cfg.data_dir / "motto-research.sqlite3")

ALLOWED_FACTORS = {
    "Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60",
    "Price_EMA_Bias_20", "Return_5", "Return_20", "Williams_R_14", "CCI_14",
    "Candle_Shape", "Vol_Surge_60", "Price_VWAP_Bias", "MFI_14", "Amihud_Illiquidity",
    "Relative_Strength", "Turn", "BIAS_20", "BIAS_60", "Vol_Ratio", "Norm_ATR_14",
    "Entity_Ratio", "Price_Cost_Bias", "Boll_Width", "Realized_Vol_20", "PV_Corr_10",
    "Overnight_Return", "CMF_20", "Trend_Strength_20",
}

FACTOR_METADATA = {
    "Relative_Strength_20": {"track": "shared", "family": "momentum", "window": 20},
    "MACD_Hist_Norm": {"track": "shared", "family": "trend", "window": 26},
    "Z_Score_20": {"track": "shared", "family": "mean_reversion", "window": 20},
    "ATR_Ratio_14_60": {"track": "shared", "family": "volatility", "window": 60},
    "Price_EMA_Bias_20": {"track": "tx", "family": "trend", "window": 20},
    "Williams_R_14": {"track": "tx", "family": "oscillator", "window": 14},
    "CCI_14": {"track": "tx", "family": "oscillator", "window": 14},
    "Candle_Shape": {"track": "tx", "family": "price_action", "window": 1},
    "Vol_Surge_60": {"track": "bs", "family": "volume", "window": 60},
    "Price_VWAP_Bias": {"track": "bs", "family": "liquidity", "window": 20},
    "MFI_14": {"track": "bs", "family": "money_flow", "window": 14},
    "Amihud_Illiquidity": {"track": "bs", "family": "liquidity", "window": 20},
    "Return_5": {"track": "shared", "family": "return", "window": 5},
    "Return_20": {"track": "shared", "family": "return", "window": 20},
    "Relative_Strength": {"track": "shared", "family": "momentum", "window": 1},
    "Turn": {"track": "bs", "family": "liquidity", "window": 1},
    "BIAS_20": {"track": "shared", "family": "trend", "window": 20},
    "BIAS_60": {"track": "shared", "family": "trend", "window": 60},
    "Vol_Ratio": {"track": "shared", "family": "volume", "window": 20},
    "Norm_ATR_14": {"track": "shared", "family": "volatility", "window": 14},
    "Entity_Ratio": {"track": "shared", "family": "price_action", "window": 1},
    "Price_Cost_Bias": {"track": "bs", "family": "liquidity", "window": 1},
    "Boll_Width": {"track": "shared", "family": "volatility", "window": 20},
    "Realized_Vol_20": {"track": "shared", "family": "volatility", "window": 20},
    "PV_Corr_10": {"track": "shared", "family": "volume", "window": 10},
    "Overnight_Return": {"track": "shared", "family": "sentiment", "window": 1},
    "CMF_20": {"track": "tx", "family": "money_flow", "window": 20},
    "Trend_Strength_20": {"track": "tx", "family": "trend", "window": 20},
}

FACTOR_PRESETS = [
    {
        "id": "condition-observation-core",
        "name": "多指标条件观察基线",
        "description": "围绕中期趋势、动能、波动与均值位置形成透明条件矩阵。",
        "scope": "baseline",
        "sourceName": "Motto 条件矩阵",
        "characteristics": "跨数据源的可解释观察基线；用于状态核验，不直接输出买卖动作。",
        "factors": ["Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60"],
        "segments": [
            {
                "name": "全市场通用",
                "factors": ["Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60"],
                "note": "相对强弱、趋势加速度、均值位置与波动扩张四类证据。",
            }
        ],
    },
    {
        "id": "tx-trend-momentum",
        "name": "腾讯财经 · 趋势价格因子组",
        "description": "由腾讯财经历史行情（经 AkShare 腾讯适配器）构建，侧重趋势延续、价格形态与波动状态。",
        "scope": "tencent-finance",
        "sourceName": "腾讯财经历史行情",
        "characteristics": "主板路径采用纯价格因子，缺少成交量时仍可运行；科技成长路径保留量价协同因子，但逐折缺失时会披露并剔除。",
        "factors": ["Relative_Strength_20", "MACD_Hist_Norm", "Price_EMA_Bias_20", "Williams_R_14", "CCI_14", "Candle_Shape"],
        "segments": [
            {
                "name": "科技成长（创业板/科创板）",
                "factors": ["Relative_Strength", "Return_5", "BIAS_20", "BIAS_60", "Vol_Ratio", "Norm_ATR_14", "Entity_Ratio", "Boll_Width", "Realized_Vol_20", "PV_Corr_10", "Overnight_Return", "CMF_20", "Trend_Strength_20"],
                "note": "强调短动量、趋势强度、波动结构、隔夜跳空及资金流协同。",
            },
            {
                "name": "主板",
                "factors": ["Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60", "Price_EMA_Bias_20", "Return_5", "Return_20", "Williams_R_14", "CCI_14", "Candle_Shape"],
                "note": "纯价格路径，强调中短期趋势、超买超卖与 K 线承接形态。",
            },
        ],
    },
    {
        "id": "bs-volume-liquidity",
        "name": "BaoStock · 量价流动性因子组",
        "description": "由 BaoStock 日线历史数据构建，侧重量能、成交成本、资金流与流动性约束。",
        "scope": "baostock",
        "sourceName": "BaoStock 日线历史数据",
        "characteristics": "量价字段更完整，适合验证资金参与度和价格冲击；低成交额与字段缺失会使流动性因子失真，因此按训练折中位数填补并披露省略项。",
        "factors": ["Vol_Surge_60", "Price_VWAP_Bias", "MFI_14", "Amihud_Illiquidity", "Return_5", "Return_20"],
        "segments": [
            {
                "name": "科技成长（创业板/科创板）",
                "factors": ["Relative_Strength", "Turn", "Return_5", "BIAS_20", "BIAS_60", "Vol_Ratio", "Norm_ATR_14", "Entity_Ratio", "Price_Cost_Bias", "Boll_Width", "Realized_Vol_20", "PV_Corr_10", "Overnight_Return"],
                "note": "强调换手、成本偏离、价量相关和高波动环境下的流动性风险。",
            },
            {
                "name": "主板",
                "factors": ["Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60", "Vol_Surge_60", "Price_VWAP_Bias", "MFI_14", "Amihud_Illiquidity", "Return_5", "Return_20"],
                "note": "同时衡量趋势、量能放大、成交成本中枢、资金流和价格冲击。",
            },
        ],
    },
]


def build_stock_analysis_messages(code: str, quote: dict, technical: dict) -> list[dict]:
    evidence = {
        "code": code,
        "quote": {
            "name": quote.get("name"),
            "price": quote.get("price"),
            "changePercent": quote.get("changePercent"),
            "marketTime": quote.get("marketTime"),
        },
        "conditions": technical.get("conditions"),
        "trend": technical.get("trend"),
        "source": technical.get("meta"),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是 本地工作台 的证据解读层。只能使用用户消息中的结构化行情证据，"
                "不得补造财务、新闻、估值或目标价。输出中文 Markdown，依次包含：结论、关键证据、"
                "冲突与风险、条件变化、数据边界。结论只能使用条件偏强/中性观察/条件偏弱/数据不足，"
                "不得给出买入、卖出、仓位或收益承诺。控制在 450 字以内。"
            ),
        },
        {"role": "user", "content": json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))},
    ]


def _job_database_path():
    path = cfg.data_dir / "research-jobs.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _persist_job(job: dict):
    with sqlite3.connect(_job_database_path()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS research_jobs (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            INSERT INTO research_jobs (id, payload, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, status=excluded.status, updated_at=excluded.updated_at
        """, (job["id"], json.dumps(job, ensure_ascii=False, default=str), job.get("status", "unknown"), datetime.now(timezone.utc).isoformat()))


def _load_job(job_id: str):
    with sqlite3.connect(_job_database_path()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS research_jobs (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        row = connection.execute("SELECT payload FROM research_jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
    return json.loads(row[0]) if row else None


def _historical_backtest_example():
    """Expose the existing audited artifact as a compact, read-only UI example."""
    artifact = Path(__file__).resolve().parent / "output" / "backtests" / "motto-local-tx-bs-dual-horizon-20260817-v2" / "factor-metrics.json"
    if not artifact.exists():
        return None
    try:
        raw = json.loads(artifact.read_text(encoding="utf-8"))
        dual = raw.get("dualHorizonResults") or {}

        def compact_package(package):
            package = package or {}

            def compact_row(row):
                row = row or {}
                result = {
                    key: row.get(key)
                    for key in ("signals", "observationDates", "outperformanceHitRate", "positiveHitRate", "averageAttentionScore")
                }
                study = row.get("returnStudy") or {}
                if study:
                    result["returnStudy"] = {
                        key: study.get(key)
                        for key in (
                            "periods", "holdingDays", "nonOverlapping", "grossAnnualizedReturn",
                            "costAdjustedAnnualizedReturn", "cumulativeNetReturn", "maxDrawdown",
                            "positivePeriodRate", "outperformanceRate", "roundTripCostBps",
                        )
                    }
                return result

            return {
                "mode": package.get("mode"),
                "horizon": package.get("horizon"),
                "primaryObjective": package.get("primaryObjective"),
                "tradeAssumption": package.get("tradeAssumption"),
                "leakageCheck": package.get("leakageCheck"),
                "foldCount": len(package.get("folds") or []),
                "tracks": {key: compact_row(value) for key, value in (package.get("tracks") or {}).items()},
                "consensus": compact_row(package.get("consensus")),
            }

        return {
            "id": "historical-example-20260817-v2",
            "mode": "backtest",
            "status": "completed",
            "origin": "read-only-local-artifact",
            "progress_message": "既有因子组合双周期回测案例；未在本次请求中重新执行",
            "created_at": "2026-08-17T00:00:00+08:00",
            "results": {
                "status": raw.get("status"),
                "stocks": raw.get("stocks") or [],
                "factors": raw.get("factors") or [],
                "observations": raw.get("observations"),
                "dataVersion": raw.get("dataVersion"),
                "dataSource": raw.get("dataSource"),
                "methodology": raw.get("methodology") or {},
                "config": raw.get("config") or {},
                "dualHorizonResults": {
                    "t1Attention": compact_package(dual.get("t1Attention")),
                    "t5Return": compact_package(dual.get("t5Return")),
                },
            },
        }
    except (OSError, ValueError, TypeError):
        return None


def _list_jobs(mode: str | None = None, limit: int = 100):
    with sqlite3.connect(_job_database_path()) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS research_jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        rows = connection.execute("SELECT payload FROM research_jobs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    jobs = [json.loads(row[0]) for row in rows]
    filtered = [job for job in jobs if mode is None or job.get("mode") == mode]
    if mode in {None, "backtest"}:
        example = _historical_backtest_example()
        if example and not any(job.get("id") == example["id"] for job in filtered):
            filtered.append(example)
    return filtered[:limit]


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if cfg.api_key and request.method != "OPTIONS" and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        if request.headers.get("authorization", "") != f"Bearer {cfg.api_key}":
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/api/health")
def health():
    vibe = {"ok": False}
    try:
        vibe = VibeResearchClient().health()
    except Exception as exc:  # Vibe is optional; core health must still be observable.
        vibe = {"ok": False, "error": str(exc)}
    return {"ok": True, "service": "motto-stock-analysis", "motto": _WORKBENCH.health(), "vibe_research": vibe}


@app.get("/api/ready")
def ready():
    result = _WORKBENCH.ready()
    return result if result["ready"] else JSONResponse(result, status_code=503)


@app.get("/api/all")
def motto_all(request: Request):
    try:
        return etag_response(request, _WORKBENCH.all())
    except Exception as exc:
        raise HTTPException(503, f"核心数据包构建失败：{str(exc)[:240]}") from exc


@app.get("/api/realtime")
def motto_realtime(request: Request):
    try:
        return etag_response(request, _WORKBENCH.realtime_patch())
    except Exception as exc:
        raise HTTPException(503, f"实时数据不可用：{str(exc)[:240]}") from exc


@app.get("/api/instruments/search")
def motto_instrument_search(q: str = Query(..., min_length=1, max_length=40), limit: int = Query(8, ge=1, le=20)):
    return _WORKBENCH.search_instruments(q, limit)


@app.get("/api/intraday")
def motto_intraday(code: str = Query(...)):
    try:
        return _WORKBENCH.intraday(code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"分时数据不可用：{str(exc)[:240]}") from exc


@app.get("/api/kline")
def motto_kline(code: str = Query(...), period: str = Query("day"), limit: int = Query(120, ge=20, le=500)):
    try:
        return _WORKBENCH.kline(code, period, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"K线数据不可用：{str(exc)[:240]}") from exc


@app.get("/api/rsi-margin")
def motto_rsi_margin(code: str = Query(...)):
    try:
        return _WORKBENCH.technical(code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"技术条件不可用：{str(exc)[:240]}") from exc


@app.get("/api/us")
def motto_us():
    try:
        package = _WORKBENCH.realtime()
        return {**package, "data": [item for item in package.get("data", []) if item.get("market") == "US"]}
    except Exception as exc:
        raise HTTPException(503, f"海外行情不可用：{str(exc)[:240]}") from exc


@app.get("/api/news")
def motto_news(code: str | None = Query(None), limit: int = Query(20, ge=1, le=50)):
    core = _WORKBENCH.news(limit)
    if core.get("data") or not _WORKBENCH.config.vibe_enabled:
        return core
    try:
        return VibeResearchClient().news(code or "market", limit)
    except Exception:
        return core


@app.get("/api/market-flows")
def motto_market_flows(kind: str = Query("industry", pattern="^(industry|concept)$")):
    return _WORKBENCH.fund_flows(kind)


@app.get("/api/valuations")
def motto_valuations(codes: str | None = Query(None)):
    values = [value.strip().upper() for value in codes.split(",") if value.strip()] if codes else None
    return _WORKBENCH.valuations(values)


@app.get("/api/margin")
def motto_margin():
    return _WORKBENCH.margin()


@app.get("/api/fund")
def motto_fund(code: str = Query(..., pattern="^[0-9]{6}$")):
    try:
        return _WORKBENCH.fund_snapshot(code)
    except Exception as exc:
        raise HTTPException(503, f"基金净值不可用：{str(exc)[:240]}") from exc


@app.get("/api/limit-pools")
def motto_limit_pools():
    return _WORKBENCH.limit_pools()


@app.get("/api/macro")
def motto_macro():
    return _WORKBENCH.macro_snapshot()


@app.get("/api/fx")
def motto_fx():
    return _WORKBENCH.fx_snapshot()


@app.get("/api/us-futures")
def motto_us_futures():
    return _WORKBENCH.us_futures()


@app.get("/api/investor-accounts")
def motto_investor_accounts():
    return _WORKBENCH.investor_accounts()


@app.get("/api/buffett-history")
def motto_buffett_history():
    return _WORKBENCH.buffett_history()


@app.get("/api/cross-market-impact")
def motto_cross_market_impact():
    return _WORKBENCH.cross_market_impact()


@app.get("/api/portfolio/capabilities")
def portfolio_capabilities():
    return _WORKBENCH.portfolio_capabilities()


@app.get("/api/portfolio-realtime")
def portfolio_realtime():
    capabilities = _WORKBENCH.portfolio_capabilities()
    if not capabilities["enabled"]:
        return JSONResponse({**capabilities, "detail": "当前为 A 模式；接口保留但未启用，且不存在任何示例持仓"}, status_code=409)
    return {"data": [], "mode": capabilities["mode"]}


@app.get("/api/extensions/vibe/status")
def vibe_extension_status():
    return {"enabled": _WORKBENCH.config.vibe_enabled, "mode": _WORKBENCH.config.vibe_mode, "optional": True}


@app.get("/api/config/status")
def config_status():
    return public_config_status()


@app.get("/api/capabilities")
def capabilities():
    return {
        "ok": True,
        "capabilities": {
            "inference": cfg.enable_model_execution,
            "training": cfg.enable_training_api,
            "backtest": cfg.enable_backtest_api,
            "custom_stocks": True,
            "custom_factors": True,
        },
    }


@app.get("/api/upstream-status")
def upstream_status():
    return _WORKBENCH.upstream_capabilities()


class StockLlmAnalysisRequest(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")
    provider: str = Field(default="deepseek", pattern=r"^(deepseek|volcengine)$")


@app.post("/api/llm/stock-analysis")
def stock_llm_analysis(body: StockLlmAnalysisRequest):
    provider = get_provider_config(body.provider)
    try:
        provider.validate()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        technical = _WORKBENCH.technical(body.code)
        realtime = _WORKBENCH.realtime()
        quote = next((row for row in realtime.get("data", []) if row.get("code") == body.code), {"code": body.code})
        messages = build_stock_analysis_messages(body.code, quote, technical)
        analysis = chat_completion_text(
            provider,
            messages,
            temperature=0.15,
            max_tokens=1200,
            extra_payload={"thinking": {"type": "disabled"}} if provider.name == "deepseek" else None,
        )
        return {
            "schemaVersion": "motto.llm-stock-analysis.v1",
            "code": body.code,
            "name": quote.get("name"),
            "provider": provider.name,
            "model": provider.model,
            "analysis": analysis,
            "evidence": {
                "conclusion": technical.get("conditions", {}).get("conclusion"),
                "marketTime": technical.get("meta", {}).get("market_time"),
                "source": technical.get("meta", {}).get("source"),
            },
            "riskNotice": "模型只解释页面已有证据，不构成买卖、仓位或收益建议。",
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(503, f"LLM 解读暂不可用：{str(exc)[:240]}") from exc
    except Exception as exc:
        raise HTTPException(503, f"个股证据或模型服务不可用：{str(exc)[:240]}") from exc


@app.get("/api/research/factors")
def research_factors():
    return {
        "schemaVersion": "motto.factor-catalog.v1",
        "records": [{"id": name, "name": name, "status": "stable", "version": 1, "formula": "built-in verified implementation", **FACTOR_METADATA[name]} for name in sorted(ALLOWED_FACTORS)] + _REGISTRY.factors(),
        "requiredAnalysis": ["coverage", "missingRate", "IC", "RankIC", "ICIR", "decay", "turnover", "correlation", "regimeStability"],
    }


@app.get("/api/research/factor-presets")
def research_factor_presets():
    return {
        "schemaVersion": "motto.factor-presets.v1",
        "records": FACTOR_PRESETS,
        "note": "导入仅填充因子选择，不自动训练、不自动回测，也不覆盖已有版本。",
    }


class FactorDefinitionRequest(BaseModel):
    id: str
    name: str
    family: str = "custom"
    track: str = "shared"
    formula: str
    description: str = ""


@app.post("/api/research/factors", status_code=201)
def create_research_factor(body: FactorDefinitionRequest):
    try:
        return _REGISTRY.create_factor(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/research/dual-track/latest")
def dual_track_latest(day: str | None = Query(None)):
    try:
        return {"comparison": latest_comparison(day), "tx": latest_predictions("tx", day), "bs": latest_predictions("bs", day), "frequency": "daily"}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404 if isinstance(exc, FileNotFoundError) else 400, str(exc)) from exc


@app.get("/api/research/backtests")
def research_backtests(limit: int = Query(20, ge=1, le=100)):
    return {"records": _list_jobs("backtest", limit), "note": "仅返回真实已提交任务；未运行时不生成占位指标"}


@app.get("/api/research/jobs")
def research_jobs(mode: str | None = Query(None), limit: int = Query(50, ge=1, le=200)):
    if mode not in {None, "training", "backtest"}:
        raise HTTPException(400, "mode must be training or backtest")
    return {"records": _list_jobs(mode, limit)}


class ModelPromotionRequest(BaseModel):
    engine: str
    job_id: str


@app.get("/api/research/models")
def research_models():
    return {"records": _REGISTRY.model_releases()}


@app.post("/api/research/models/promote")
def promote_model(body: ModelPromotionRequest):
    job = _load_job(body.job_id)
    if not job:
        raise HTTPException(404, "training job not found")
    try:
        return _REGISTRY.promote(body.engine, job)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/research/models/{engine}/rollback")
def rollback_model(engine: str):
    try:
        return _REGISTRY.rollback(engine)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/predictions/{engine}")
def predictions(engine: str, day: str | None = Query(None)):
    try:
        return latest_predictions(engine, day)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404 if isinstance(exc, FileNotFoundError) else 400, str(exc)) from exc


@app.get("/api/comparison")
def comparison(day: str | None = Query(None)):
    try:
        return latest_comparison(day)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404 if isinstance(exc, FileNotFoundError) else 400, str(exc)) from exc


@app.get("/api/vibe/quote")
def vibe_quote(codes: str = Query(...)):
    try:
        return VibeResearchClient().quote([x.strip() for x in codes.split(",") if x.strip()])
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/vibe/valuation")
def vibe_valuation(code: str = Query(...)):
    try:
        return VibeResearchClient().valuation(code)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


class RunRequest(BaseModel):
    holdings: str = ""


class JobRequest(BaseModel):
    mode: str
    engine: str = "both"
    stocks: list[str] = Field(default_factory=list)
    factors: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    config: dict[str, object] = Field(default_factory=dict)


class UniverseValidationRequest(BaseModel):
    stocks: list[str] = Field(default_factory=list)
    date_from: str = "2021-01-01"
    date_to: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())


@app.post("/api/universe/validate")
def validate_universe(body: UniverseValidationRequest):
    stocks = list(dict.fromkeys(code.strip().upper() for code in body.stocks if code.strip()))[:50]
    if not stocks or any(not (code.isdigit() and len(code) == 6) for code in stocks):
        raise HTTPException(400, "当前数据预检仅支持 1-50 个六位 A 股代码")
    try:
        import akshare as ak
    except ImportError as exc:
        raise HTTPException(503, "研究执行器缺少 AkShare 数据适配器") from exc
    start = body.date_from.replace("-", "")
    end = body.date_to.replace("-", "")
    expected = max(1, int((datetime.fromisoformat(body.date_to) - datetime.fromisoformat(body.date_from)).days * 250 / 365))
    results = []
    for code in stocks:
        symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
        try:
            raw = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end, adjust="qfq")
            rows = int(len(raw))
            index = raw.index if rows else []
            history_start = str(index.min().date()) if rows and hasattr(index.min(), "date") else (str(index.min())[:10] if rows else None)
            coverage = min(1.0, rows / expected)
            results.append({"code": code, "status": "ready" if rows >= 120 else "warning", "coverage": round(coverage, 4), "observations": rows, "historyStart": history_start, "message": "" if rows >= 120 else f"仅有 {rows} 个交易日，建议至少 120 个"})
        except Exception as exc:
            results.append({"code": code, "status": "warning", "coverage": 0, "observations": 0, "historyStart": None, "message": str(exc)[:160]})
    return {"ok": True, "dateFrom": body.date_from, "dateTo": body.date_to, "results": results}


def _set_job(job_id: str, **changes):
    snapshot = None
    with _JOBS_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(changes)
            snapshot = dict(_JOBS[job_id])
    if snapshot:
        _persist_job(snapshot)


def _run_training(job_id: str, body: JobRequest):
    if not _TRAIN_LOCK.acquire(blocking=False):
        _set_job(job_id, status="failed", error="another training job is already running")
        return
    try:
        _set_job(job_id, status="running", progress=5, progress_message="正在准备独立训练目录", started_at=datetime.now(timezone.utc).isoformat())
        output_root = (cfg.training_runs_dir or (cfg.data_dir / "training-runs")) / job_id
        output_root.mkdir(parents=True, exist_ok=False)
        results = {}
        if body.engine in {"tx", "both"}:
            _set_job(job_id, progress=15, progress_message="正在训练 TX 轨道")
            from quant.train_mainboard_tx import train as train_tx
            results["tx"] = train_tx(body.stocks, body.factors, output_root / "tx")
        if body.engine in {"bs", "both"}:
            _set_job(job_id, progress=55 if body.engine == "both" else 15, progress_message="正在训练 BS 轨道")
            from quant.train_mainboard_bs import train as train_bs
            results["bs"] = train_bs(body.stocks, body.factors, output_root / "bs")
        _set_job(job_id, status="completed", progress=100, progress_message="训练完成", completed_at=datetime.now(timezone.utc).isoformat(), output_dir=str(output_root), results=results)
    except Exception as exc:
        _set_job(job_id, status="failed", completed_at=datetime.now(timezone.utc).isoformat(), error=str(exc))
    finally:
        _TRAIN_LOCK.release()


def _run_backtest(job_id: str, body: JobRequest):
    if not _BACKTEST_LOCK.acquire(blocking=False):
        _set_job(job_id, status="failed", error="another backtest job is already running")
        return
    try:
        _set_job(job_id, status="running", progress=10, progress_message="正在拉取并校验历史数据", started_at=datetime.now(timezone.utc).isoformat())
        from quant.factor_backtest import run_factor_backtest
        output_root = (cfg.training_runs_dir or (cfg.data_dir / "training-runs")) / job_id / "backtest"
        result = run_factor_backtest(body.stocks, body.factors, body.config, output_root, body.weights)
        _set_job(job_id, status="completed", progress=100, progress_message="回测完成", completed_at=datetime.now(timezone.utc).isoformat(), output_dir=str(output_root), results=result)
    except Exception as exc:
        _set_job(job_id, status="failed", completed_at=datetime.now(timezone.utc).isoformat(), error=str(exc))
    finally:
        _BACKTEST_LOCK.release()


@app.post("/api/jobs", status_code=202)
def create_job(body: JobRequest):
    if body.mode not in {"training", "backtest"}:
        raise HTTPException(400, "mode 目前只支持 training 或 backtest")
    if body.mode == "training" and not cfg.enable_training_api:
        raise HTTPException(403, "训练 API 默认关闭；确认独立实验目录与运行资源后设置 ENABLE_TRAINING_API=1")
    if body.mode == "backtest" and not cfg.enable_backtest_api:
        raise HTTPException(403, "回测 API 默认关闭；确认历史数据授权与运行资源后设置 ENABLE_BACKTEST_API=1")
    if body.engine not in {"tx", "bs", "both"}:
        raise HTTPException(400, "engine 只能是 tx、bs 或 both")
    stocks = [code.strip().upper() for code in body.stocks if code.strip()]
    maximum = 20 if body.mode == "training" else 50
    minimum = 1 if body.mode == "training" else 3
    if len(stocks) < minimum or len(stocks) > maximum or any(not (code.isdigit() and len(code) == 6) for code in stocks):
        raise HTTPException(400, f"当前{body.mode}执行器支持 {minimum}-{maximum} 个六位 A 股代码")
    custom_formulas = _REGISTRY.latest_factor_formulas()
    factors = [factor for factor in body.factors if factor in ALLOWED_FACTORS or factor in custom_formulas]
    if len(factors) < 3:
        raise HTTPException(400, "训练或回测至少需要 3 个兼容因子")
    if body.mode == "training" and any(name in custom_formulas for name in factors):
        raise HTTPException(400, "自定义公式因子须先通过真实回测验证；当前训练器只接受已实现的稳定因子")
    body.config = {**body.config, "customFactorFormulas": {name: custom_formulas[name] for name in factors if name in custom_formulas}}
    tx_factors = {"Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60", "Price_EMA_Bias_20", "Return_5", "Return_20", "Williams_R_14", "CCI_14", "Candle_Shape"}
    bs_factors = {"Relative_Strength_20", "MACD_Hist_Norm", "Z_Score_20", "ATR_Ratio_14_60", "Vol_Surge_60", "Price_VWAP_Bias", "MFI_14", "Amihud_Illiquidity", "Return_5", "Return_20"}
    if body.mode == "training" and body.engine in {"tx", "both"} and len(tx_factors.intersection(factors)) < 3:
        raise HTTPException(400, "TX 轨道至少需要 3 个 TX 兼容因子")
    if body.mode == "training" and body.engine in {"bs", "both"} and len(bs_factors.intersection(factors)) < 3:
        raise HTTPException(400, "BS 轨道至少需要 3 个 BS 兼容因子")
    body.stocks = stocks
    body.factors = factors
    body.weights = {name: float(value) for name, value in body.weights.items() if name in factors and 0 <= float(value) <= 1}
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "mode": body.mode,
        "engine": body.engine,
        "stocks": stocks,
        "factors": factors,
        "weights": body.weights,
        "config": body.config,
        "status": "queued",
        "progress": 0,
        "progress_message": "任务已进入持久化队列",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _JOBS_LOCK:
        _JOBS[job_id] = job
    _persist_job(job)
    target = _run_training if body.mode == "training" else _run_backtest
    threading.Thread(target=target, args=(job_id, body), daemon=True).start()
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        job = _load_job(job_id)
    if not job:
        raise HTTPException(404, "research job not found")
    return job


@app.post("/api/run/{engine}")
def run_engine(engine: str, body: RunRequest):
    if not cfg.enable_model_execution:
        raise HTTPException(403, "模型执行 API 默认关闭；确认仅本机使用后设置 ENABLE_MODEL_EXECUTION_API=1")
    if engine not in {"tx", "bs", "both"}:
        raise HTTPException(400, "engine 只能是 tx、bs 或 both")
    if not _RUN_LOCK.acquire(blocking=False):
        raise HTTPException(409, "已有模型任务正在运行")
    try:
        tx_raw = bs_raw = None
        tx_report = bs_report = None
        if engine in {"tx", "both"}:
            from quant.predict_tx import run_daily_check
            tx_raw, tx_report = run_daily_check(body.holdings)
        if engine in {"bs", "both"}:
            from quant.predict_bs import run_daily_check_bs
            bs_raw, bs_report = run_daily_check_bs(body.holdings)
        result = {
            "tx": normalize_predictions(tx_raw or {}, "tx") if tx_raw is not None else None,
            "bs": normalize_predictions(bs_raw or {}, "bs") if bs_raw is not None else None,
            "reports": {"tx": tx_report, "bs": bs_report},
        }
        if tx_raw is not None and bs_raw is not None:
            result["comparison"] = compare_prediction_sets(tx_raw, bs_raw, cfg.consensus_threshold)
        return result
    finally:
        _RUN_LOCK.release()
