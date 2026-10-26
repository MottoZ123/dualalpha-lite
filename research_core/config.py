"""Environment-backed configuration with no secrets committed to source."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: str | Path | None = None) -> None:
    """Load a small .env file without adding a python-dotenv dependency.

    Existing process variables always win. The parser intentionally supports only
    KEY=VALUE lines because secrets should not execute shell expressions.
    """

    env_path = Path(path) if path else PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: int
    max_retries: int
    thinking_mode: str | None = None
    reasoning_effort: str | None = None

    def validate(self) -> None:
        missing = []
        if not self.api_key:
            missing.append(f"{self.name.upper()}_API_KEY")
        if not self.model:
            missing.append(f"{self.name.upper()}_MODEL")
        if not self.base_url:
            missing.append(f"{self.name.upper()}_BASE_URL")
        if missing:
            raise RuntimeError("缺少模型配置：" + ", ".join(missing) + "。请复制 .env.example 为 .env 后填写。")


def get_provider_config(name: str) -> ProviderConfig:
    provider = name.strip().lower()
    defaults = {
        "volcengine": {
            "model": "",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        },
        "deepseek": {
            "model": "deepseek-v4-pro",
            "base_url": "https://api.deepseek.com/chat/completions",
        },
    }
    if provider not in defaults:
        raise ValueError(f"不支持的 LLM provider: {name}")
    prefix = provider.upper()
    thinking_mode = None
    reasoning_effort = None
    if provider == "deepseek":
        thinking_mode = os.getenv("DEEPSEEK_THINKING", "enabled").strip().lower()
        if thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("DEEPSEEK_THINKING 只能是 enabled 或 disabled")
        reasoning_effort = os.getenv("DEEPSEEK_REASONING_EFFORT", "high").strip().lower()
        if reasoning_effort not in {"high", "max"}:
            raise ValueError("DEEPSEEK_REASONING_EFFORT 只能是 high 或 max")
    return ProviderConfig(
        name=provider,
        api_key=os.getenv(f"{prefix}_API_KEY", "").strip(),
        model=os.getenv(f"{prefix}_MODEL", defaults[provider]["model"]).strip(),
        base_url=os.getenv(f"{prefix}_BASE_URL", defaults[provider]["base_url"]).strip(),
        timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 240),
        max_retries=_int("LLM_MAX_RETRIES", 3),
        thinking_mode=thinking_mode,
        reasoning_effort=reasoning_effort,
    )


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    reports_dir: Path
    vibe_base_url: str
    vibe_api_key: str
    vibe_timeout_seconds: int
    api_key: str
    allow_origins: tuple[str, ...]
    consensus_threshold: float
    enable_model_execution: bool
    enable_training_api: bool = False
    enable_backtest_api: bool = False
    training_runs_dir: Path | None = None


def get_app_config() -> AppConfig:
    data_value = os.getenv("RESEARCH_DATA_DIR", "").strip()
    reports_value = os.getenv("RESEARCH_REPORTS_DIR", "").strip()
    data_dir = Path(data_value or str(Path.home() / ".quant-research")).expanduser()
    reports_dir = Path(reports_value or str(PROJECT_ROOT / "AB_Test_Reports")).expanduser()
    origins = tuple(x.strip() for x in os.getenv("RESEARCH_ALLOW_ORIGINS", "http://127.0.0.1:5899,http://localhost:5899").split(",") if x.strip())
    return AppConfig(
        data_dir=data_dir,
        reports_dir=reports_dir,
        vibe_base_url=os.getenv("VIBE_RESEARCH_BASE_URL", "http://127.0.0.1:8900").rstrip("/"),
        vibe_api_key=os.getenv("VIBE_RESEARCH_API_KEY", "").strip(),
        vibe_timeout_seconds=_int("VIBE_RESEARCH_TIMEOUT_SECONDS", 20),
        api_key=os.getenv("RESEARCH_API_KEY", "").strip(),
        allow_origins=origins,
        consensus_threshold=_float("CONSENSUS_THRESHOLD", 0.53),
        enable_model_execution=_bool("ENABLE_MODEL_EXECUTION_API", False),
        enable_training_api=_bool("ENABLE_TRAINING_API", False),
        enable_backtest_api=_bool("ENABLE_BACKTEST_API", False),
        training_runs_dir=Path(os.getenv("TRAINING_RUNS_DIR", "").strip() or str(data_dir / "training-runs")).expanduser(),
    )


def public_config_status() -> dict:
    """Return configuration readiness without ever returning secret values."""

    app = get_app_config()
    providers = {}
    for name in ("volcengine", "deepseek"):
        cfg = get_provider_config(name)
        providers[name] = {
            "configured": bool(cfg.api_key and cfg.model and cfg.base_url),
            "model": cfg.model,
            "base_url": cfg.base_url,
        }
    return {
        "providers": providers,
        "vibe_research": {"base_url": app.vibe_base_url, "api_key_configured": bool(app.vibe_api_key)},
        "api_auth_enabled": bool(app.api_key),
        "model_execution_enabled": app.enable_model_execution,
        "training_api_enabled": app.enable_training_api,
        "backtest_api_enabled": app.enable_backtest_api,
        "reports_dir": str(app.reports_dir),
        "consensus_threshold": app.consensus_threshold,
    }
