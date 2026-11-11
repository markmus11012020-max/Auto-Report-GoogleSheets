"""Тесты генератора данных отчётов."""

from __future__ import annotations

import unittest
from datetime import date

from report_data import (
    REPORT_TYPES,
    ReportDataGenerator,
    parse_date,
    validate_period,
)

START = date(2026, 10, 1)
END = date(2026, 10, 31)


class ReportDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = ReportDataGenerator(seed=42)

    def test_all_report_types_have_valid_structure(self) -> None:
        for report_type in REPORT_TYPES:
            with self.subTest(report_type=report_type):
                report = self.generator.generate(
                    report_type, START, END, "Отдел продаж", "Тестовый автор"
                )
                self.assertGreaterEqual(len(report.rows), 10)
                self.assertLessEqual(len(report.rows), 30)
                self.assertEqual(len(report.columns), 6)
                self.assertEqual(len(report.totals), 6)
                self.assertEqual(len(report.kpis), 5)
                for row in report.rows:
                    self.assertEqual(len(row), 6)
                for kpi in report.kpis:
                    self.assertTrue(kpi.name)
                    self.assertTrue(kpi.unit)

    def test_determinism_with_seed(self) -> None:
        first = self.generator.generate("Продажи", START, END)
        second = self.generator.generate("Продажи", START, END)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_different_seeds_produce_different_data(self) -> None:
        first = ReportDataGenerator(seed=1).generate("Маркетинг", START, END)
        second = ReportDataGenerator(seed=2).generate("Маркетинг", START, END)
        self.assertNotEqual(first.to_dict(), second.to_dict())

    def test_sales_shares_sum_to_one(self) -> None:
        report = self.generator.generate("Продажи", START, END)
        shares = sum(row[5] for row in report.rows)
        self.assertAlmostEqual(shares, 1.0, places=3)
        self.assertAlmostEqual(report.totals[5], 1.0, places=3)

    def test_sales_totals_match_rows(self) -> None:
        report = self.generator.generate("Продажи", START, END)
        operations = sum(row[2] for row in report.rows)
        total = sum(row[3] for row in report.rows)
        self.assertEqual(report.totals[2], operations)
        self.assertAlmostEqual(report.totals[3], total, places=2)

    def test_marketing_totals_match_rows(self) -> None:
        report = self.generator.generate("Маркетинг", START, END)
        self.assertEqual(report.totals[1], sum(row[1] for row in report.rows))
        self.assertEqual(report.totals[2], sum(row[2] for row in report.rows))
        self.assertEqual(report.totals[4], round(sum(row[4] for row in report.rows), 2))
        self.assertEqual(report.totals[5], sum(row[5] for row in report.rows))

    def test_ai_context_is_serializable(self) -> None:
        import json

        report = self.generator.generate("Финансы", START, END, "Финансовый отдел")
        payload = json.dumps(report.to_ai_context(), ensure_ascii=False)
        self.assertIn("report_type", payload)
        self.assertIn("kpis", payload)

    def test_unknown_report_type(self) -> None:
        with self.assertRaises(ValueError):
            self.generator.generate("Неизвестный", START, END)

    def test_invalid_period(self) -> None:
        with self.assertRaises(ValueError):
            self.generator.generate("Продажи", END, START)


class ValidationTests(unittest.TestCase):
    def test_validate_period_ok(self) -> None:
        self.assertEqual(validate_period(START, END, today=date(2026, 11, 11)), [])

    def test_validate_period_reversed(self) -> None:
        errors = validate_period(END, START, today=date(2026, 11, 11))
        self.assertTrue(errors)

    def test_validate_period_future(self) -> None:
        errors = validate_period(date(2026, 11, 1), date(2026, 12, 1), today=date(2026, 11, 11))
        self.assertTrue(any("позже текущей" in error for error in errors))

    def test_validate_period_too_long(self) -> None:
        errors = validate_period(date(2024, 1, 1), date(2026, 1, 1), today=date(2026, 11, 11))
        self.assertTrue(any("366" in error for error in errors))

    def test_parse_date(self) -> None:
        self.assertEqual(parse_date("01.10.2026"), START)
        self.assertEqual(parse_date("2026-10-01"), START)
        with self.assertRaises(ValueError):
            parse_date("32.13.2026")


if __name__ == "__main__":
    unittest.main()
