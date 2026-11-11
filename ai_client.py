"""Клиент OpenAI-совместимого API AITunnel.

Генерирует аналитический текст отчёта. При недоступности провайдера
возвращает резервный текст, построенный на данных отчёта, — генерация
отчёта при этом не прерывается.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from config import Settings, get_logger

LOGGER = get_logger("ai")

SYSTEM_PROMPT = (
    "Ты — опытный бизнес-аналитик. Пиши на русском языке деловым стилем. "
    "Сформулируй вывод объёмом 5–7 предложений. Не используй markdown, списки, "
    "заголовки и эмодзи. Не выдумывай цифры: используй только переданные данные. "
    "Структура: общая динамика, ключевой драйвер, риск, рекомендация."
)


@dataclass
class AIResult:
    text: str
    used_fallback: bool = False
    error: str | None = None


class AITunnelClient:
    """Генерация текста через AITunnel (OpenAI-совместимый API)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        retries: int = 2,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self.timeout = timeout
        self.retries = max(0, retries)

    @classmethod
    def from_settings(cls, settings: Settings) -> "AITunnelClient":
        return cls(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            timeout=settings.ai_timeout,
            retries=settings.ai_retries,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def generate_summary(self, context: dict[str, Any]) -> AIResult:
        """Вернуть аналитический текст и признак использования резерва."""

        if not self.configured:
            LOGGER.warning("ИИ не настроен — используется резервный текст")
            return AIResult(
                text=self.fallback_summary(context),
                used_fallback=True,
                error="ИИ не настроен (проверьте AITUNNEL_API_KEY в .env)",
            )

        system_prompt, user_prompt = self._build_prompt(context)
        last_error = ""
        max_tokens = 3000

        for attempt in range(self.retries + 1):
            try:
                text, finish_reason = self._call_api(system_prompt, user_prompt, max_tokens)
                if finish_reason == "length":
                    last_error = "Ответ модели обрезан по лимиту токенов"
                    max_tokens = min(max_tokens * 2, 4000)
                    LOGGER.warning(
                        "ИИ: ответ обрезан, увеличиваю лимит до %s токенов", max_tokens
                    )
                    continue
                cleaned = self._sanitize(text)
                if cleaned:
                    LOGGER.info(
                        "ИИ: модель=%s, символов=%s, попытка=%s",
                        self.model,
                        len(cleaned),
                        attempt + 1,
                    )
                    return AIResult(text=cleaned)
                last_error = "Пустой ответ модели"
            except Exception as exc:  # noqa: BLE001 - нужен fallback при любой ошибке
                last_error = str(exc)
                LOGGER.warning(
                    "ИИ: попытка %s из %s завершилась ошибкой: %s",
                    attempt + 1,
                    self.retries + 1,
                    last_error,
                )
                if self._is_auth_error(last_error):
                    break
                if attempt < self.retries:
                    time.sleep(2**attempt)

        LOGGER.warning("ИИ недоступен, используется резервный текст")
        return AIResult(
            text=self.fallback_summary(context),
            used_fallback=True,
            error=last_error,
        )

    # ------------------------------------------------------------------
    def _call_api(self, system_prompt: str, user_prompt: str, max_tokens: int) -> tuple[str, str | None]:
        try:
            from openai import OpenAI
        except ImportError as exc:  # noqa: TRY003
            raise RuntimeError(
                "Не установлен пакет openai. Выполните: pip install -r requirements.txt"
            ) from exc

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        if not response.choices:
            raise RuntimeError("Провайдер вернул ответ без вариантов")
        choice = response.choices[0]
        return choice.message.content or "", choice.finish_reason

    @staticmethod
    def _build_prompt(context: dict[str, Any]) -> tuple[str, str]:
        payload = json.dumps(context, ensure_ascii=False, indent=2)
        user_prompt = (
            "Данные отчёта в формате JSON:\n"
            f"{payload}\n\n"
            "Напиши аналитический вывод по этому отчёту: динамика, ключевой "
            "драйвер, риск и одна конкретная рекомендация."
        )
        return SYSTEM_PROMPT, user_prompt

    @staticmethod
    def _sanitize(text: str) -> str:
        value = (text or "").strip()
        value = re.sub(r"`{1,3}", "", value)
        value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
        value = re.sub(r"^#{1,6}\s*", "", value, flags=re.MULTILINE)
        value = re.sub(r"^\s*[-*•]\s+", "", value, flags=re.MULTILINE)
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) > 1500:
            value = value[:1500].rsplit(".", 1)[0] + "."
        if value and value[-1] not in ".!?":
            value += "."
        return value

    @staticmethod
    def _is_auth_error(message: str) -> bool:
        lowered = message.lower()
        return any(
            marker in lowered
            for marker in ("401", "invalid api key", "incorrect api key", "unauthorized")
        )

    # ------------------------------------------------------------------
    def fallback_summary(self, context: dict[str, Any]) -> str:
        """Резервный аналитический текст на основе данных отчёта."""

        report_type = context.get("report_type", "Отчёт")
        period = context.get("period", "")
        department = context.get("department", "")
        kpis = context.get("kpis", []) or []

        def kpi_text(item: dict[str, Any]) -> str:
            return f"{item.get('name', '')} — {item.get('value', '')}".strip()

        if not kpis:
            return (
                f"За период {period} сформирован отчёт «{report_type}». "
                "Данные доступны в таблице. Рекомендуется проверить ключевые "
                "показатели и сравнить их с предыдущим периодом."
            )

        main = kpis[0]
        parts: list[str] = []
        parts.append(
            f"За период {period} по направлению «{report_type}» "
            f"показатель «{main.get('name', '')}» составил {main.get('value', '')}."
        )

        change = main.get("change_pct")
        if isinstance(change, (int, float)):
            if change > 0:
                parts.append(f"Относительно предыдущего периода рост составил {change:.1f}%.")
            elif change < 0:
                parts.append(f"Относительно предыдущего периода снижение составило {abs(change):.1f}%.")
            else:
                parts.append("Динамика относительно предыдущего периода нейтральная.")

        if len(kpis) > 1:
            secondary = "; ".join(kpi_text(item) for item in kpis[1:4])
            parts.append(f"Дополнительные показатели: {secondary}.")

        changes = [
            (item.get("name", ""), item.get("change_pct"))
            for item in kpis
            if isinstance(item.get("change_pct"), (int, float))
        ]
        if changes:
            worst_name, worst_change = min(changes, key=lambda pair: pair[1])
            if worst_change < 0:
                parts.append(
                    f"Зона риска — «{worst_name}»: снижение на {abs(worst_change):.1f}% "
                    "к предыдущему периоду."
                )

        rows = context.get("top_rows", []) or []
        if rows:
            first_row = rows[0].get("row", {})
            label = next((str(value) for value in first_row.values() if value), "")
            if label:
                parts.append(f"Наибольший вклад в результат внесла позиция «{label}».")

        if department and department != "Все подразделения":
            parts.append(f"Отчёт сформирован по подразделению «{department}».")

        parts.append(
            "Рекомендуется детально проверить показатели с отрицательной динамикой "
            "и скорректировать план на следующий период."
        )
        return " ".join(parts)
