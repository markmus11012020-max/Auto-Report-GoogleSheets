"""Тесты ИИ-клиента (без сетевых вызовов)."""

from __future__ import annotations

import unittest

from ai_client import AITunnelClient

CONTEXT = {
    "report_type": "Продажи",
    "period": "01.10.2026 — 31.10.2026",
    "department": "Отдел продаж",
    "kpis": [
        {"name": "Выручка", "value": "1 234 567,89 ₽", "change_pct": 12.5},
        {"name": "Количество операций", "value": "1 200 шт.", "change_pct": -3.2},
    ],
    "top_rows": [{"row": {"Дата": "01.10.2026", "Категория": "Электроника"}}],
}


class AIClientTests(unittest.TestCase):
    def test_unconfigured_client_uses_fallback(self) -> None:
        client = AITunnelClient("", "", "")
        self.assertFalse(client.configured)
        result = client.generate_summary(CONTEXT)
        self.assertTrue(result.used_fallback)
        self.assertIn("Выручка", result.text)
        self.assertIn("01.10.2026", result.text)
        self.assertGreater(len(result.text), 100)

    def test_fallback_mentions_negative_dynamics(self) -> None:
        text = AITunnelClient("", "", "").fallback_summary(CONTEXT)
        self.assertIn("риска", text)
        self.assertIn("Количество операций", text)

    def test_sanitize_removes_markdown(self) -> None:
        raw = "**Вывод:**\n\n- пункт один\n- пункт два\n\n`код`"
        cleaned = AITunnelClient._sanitize(raw)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("- ", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertTrue(cleaned.endswith("."))

    def test_prompt_contains_period(self) -> None:
        system, user = AITunnelClient._build_prompt(CONTEXT)
        self.assertIn("аналитик", system)
        self.assertIn("01.10.2026", user)
        self.assertIn("JSON", user)

    def test_auth_error_detection(self) -> None:
        self.assertTrue(AITunnelClient._is_auth_error("Error 401: Unauthorized"))
        self.assertTrue(AITunnelClient._is_auth_error("invalid api key"))
        self.assertFalse(AITunnelClient._is_auth_error("connection timeout"))


if __name__ == "__main__":
    unittest.main()
