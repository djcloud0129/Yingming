from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any


LOCAL_SETTINGS_PATH = Path("data") / "local_settings.json"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class ModelSettings:
    provider: str = "openai-compatible"
    api_key: str = ""
    base_url: str = DEFAULT_OPENAI_BASE_URL
    model: str = DEFAULT_OPENAI_MODEL
    temperature: float = 0.8
    auto_memory: bool = True
    deepseek_thinking: str = "disabled"
    deepseek_reasoning_effort: str = "high"

    @property
    def is_deepseek(self) -> bool:
        return self.provider.lower() == "deepseek" or "deepseek.com" in self.base_url.lower()

    @property
    def display_name(self) -> str:
        if self.is_deepseek:
            return f"DeepSeek: {self.model}"
        return self.model


def local_settings_file(project_root: Path) -> Path:
    return project_root / LOCAL_SETTINGS_PATH


def load_model_settings(project_root: Path | None = None) -> ModelSettings:
    values: dict[str, Any] = asdict(ModelSettings())

    if project_root is not None:
        values.update(_read_local_model_settings(local_settings_file(project_root)))

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    yingming_key = os.getenv("YINGMING_API_KEY", "")

    if deepseek_key and not _env_any("YINGMING_BASE_URL", "YINGMING_MODEL"):
        values["provider"] = "deepseek"
        values["base_url"] = DEFAULT_DEEPSEEK_BASE_URL
        values["model"] = DEFAULT_DEEPSEEK_MODEL

    env_overrides = {
        "api_key": yingming_key or deepseek_key or openai_key,
        "base_url": os.getenv("YINGMING_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL"),
        "model": os.getenv("YINGMING_MODEL") or os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL"),
        "temperature": os.getenv("YINGMING_TEMPERATURE"),
        "auto_memory": os.getenv("YINGMING_AUTO_MEMORY"),
        "deepseek_thinking": os.getenv("DEEPSEEK_THINKING"),
        "deepseek_reasoning_effort": os.getenv("DEEPSEEK_REASONING_EFFORT"),
    }
    for key, value in env_overrides.items():
        if value not in (None, ""):
            values[key] = value

    if values.get("api_key") == deepseek_key and deepseek_key:
        values["provider"] = "deepseek"

    return _coerce_settings(values)


def save_model_settings(project_root: Path, settings: ModelSettings) -> Path:
    path = local_settings_file(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                data = existing
        except json.JSONDecodeError:
            data = {}

    data["model"] = asdict(settings)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def redacted_model_settings(settings: ModelSettings) -> dict[str, Any]:
    data = asdict(settings)
    data["api_key"] = "已保存" if settings.api_key else ""
    data["available"] = bool(settings.api_key)
    data["display_name"] = settings.display_name if settings.api_key else "离线模式"
    return data


def deepseek_default_settings(api_key: str = "") -> ModelSettings:
    return ModelSettings(
        provider="deepseek",
        api_key=api_key,
        base_url=DEFAULT_DEEPSEEK_BASE_URL,
        model=DEFAULT_DEEPSEEK_MODEL,
        temperature=0.8,
        auto_memory=True,
        deepseek_thinking="disabled",
        deepseek_reasoning_effort="high",
    )


def _read_local_model_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    model = data.get("model", data)
    return model if isinstance(model, dict) else {}


def _coerce_settings(values: dict[str, Any]) -> ModelSettings:
    provider = str(values.get("provider") or "openai-compatible").strip() or "openai-compatible"
    api_key = str(values.get("api_key") or "").strip()
    base_url = str(values.get("base_url") or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    model = str(values.get("model") or DEFAULT_OPENAI_MODEL).strip()
    temperature = _coerce_float(values.get("temperature"), default=0.8)
    auto_memory = _coerce_bool(values.get("auto_memory"), default=True)
    deepseek_thinking = str(values.get("deepseek_thinking") or "disabled").strip().lower()
    if deepseek_thinking not in {"enabled", "disabled", "auto"}:
        deepseek_thinking = "disabled"
    deepseek_reasoning_effort = str(values.get("deepseek_reasoning_effort") or "high").strip().lower()
    if deepseek_reasoning_effort not in {"high", "max"}:
        deepseek_reasoning_effort = "high"

    return ModelSettings(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        auto_memory=auto_memory,
        deepseek_thinking=deepseek_thinking,
        deepseek_reasoning_effort=deepseek_reasoning_effort,
    )


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _env_any(*names: str) -> bool:
    return any(bool(os.getenv(name)) for name in names)
