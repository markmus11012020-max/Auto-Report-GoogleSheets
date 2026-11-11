"""Конфигурация приложения Excel Factory.

Все параметры читаются из переменных окружения (файл .env в корне проекта).
Секреты в исходный код не попадают.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

DEFAULT_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
DEFAULT_AI_BASE_URL = "https://api.aitunnel.ru/v1"
DEFAULT_AI_MODEL = "deepseek-v4.1-flash-1017"


class ConfigError(Exception):
    """Ошибка конфигурации приложения."""


def _read_int(name: str, default: int | None) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть целым числом, получено: {raw!r}") from exc


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть числом, получено: {raw!r}") from exc


def _resolve_path(raw: str, default: str) -> Path:
    value = (raw or default).strip().strip('"').strip("'")
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass(frozen=True)
class Settings:
    """Настройки приложения."""

    project_dir: Path
    credentials_file: Path
    spreadsheet_id: str
    scopes: tuple[str, ...]

    ai_api_key: str
    ai_base_url: str
    ai_model: str
    ai_timeout: float
    ai_retries: int

    log_level: str
    report_seed: int | None
    cache_dir: Path = field(default_factory=lambda: BASE_DIR / "cache")
    logs_dir: Path = field(default_factory=lambda: BASE_DIR / "logs")

    # --- проверки ---------------------------------------------------------
    def google_problems(self) -> list[str]:
        problems: list[str] = []
        if not self.spreadsheet_id:
            problems.append("Не задан SPREADSHEET_ID в файле .env")
        if not self.credentials_file.exists():
            problems.append(
                f"Не найден JSON-ключ сервисного аккаунта: {self.credentials_file}"
            )
        return problems

    def ai_problems(self) -> list[str]:
        if not self.ai_api_key:
            return ["Не задан AITUNNEL_API_KEY в файле .env"]
        if not self.ai_base_url:
            return ["Не задан AITUNNEL_BASE_URL в файле .env"]
        if not self.ai_model:
            return ["Не задан AITUNNEL_MODEL в файле .env"]
        return []

    @property
    def ai_enabled(self) -> bool:
        return not self.ai_problems()

    def ensure_directories(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Загрузить настройки из окружения (кешируется)."""

    scopes_raw = os.getenv("GOOGLE_SCOPES", "").strip()
    scopes = (
        tuple(part.strip() for part in scopes_raw.split(",") if part.strip())
        if scopes_raw
        else DEFAULT_SCOPES
    )

    settings = Settings(
        project_dir=BASE_DIR,
        credentials_file=_resolve_path(
            os.getenv("GOOGLE_CREDENTIALS_FILE", ""), "service_account.json"
        ),
        spreadsheet_id=os.getenv("SPREADSHEET_ID", "").strip(),
        scopes=scopes,
        ai_api_key=os.getenv("AITUNNEL_API_KEY", "").strip(),
        ai_base_url=os.getenv("AITUNNEL_BASE_URL", DEFAULT_AI_BASE_URL).strip(),
        ai_model=os.getenv("AITUNNEL_MODEL", DEFAULT_AI_MODEL).strip(),
        ai_timeout=_read_float("AI_TIMEOUT", 30.0),
        ai_retries=_read_int("AI_RETRIES", 2) or 0,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        report_seed=_read_int("REPORT_SEED", None),
        cache_dir=BASE_DIR / "cache",
        logs_dir=BASE_DIR / "logs",
    )
    settings.ensure_directories()
    return settings


def setup_logging(settings: Settings | None = None) -> logging.Logger:
    """Настроить журналирование в файл и консоль (идемпотентно)."""

    settings = settings or get_settings()
    logger = logging.getLogger("excel_factory")
    if getattr(logger, "_excel_factory_configured", False):
        return logger

    logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%d.%m.%Y %H:%M:%S",
    )

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.logs_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logger.propagate = False
    logger._excel_factory_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    """Дочерний журнал приложения."""

    return logging.getLogger(f"excel_factory.{name}")
