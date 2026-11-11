"""Тесты компоновщика отчёта."""

from __future__ import annotations

import unittest
from datetime import date

from report_builder import (
    DATA_FIRST_ROW,
    KPI_FIRST_ROW,
    TABLE_HEADER_ROW,
    TITLE_ROW,
    ReportBuilder,
)
from report_data import ReportDataGenerator

START = date(2026, 10, 1)
END = date(2026, 10, 31)


class ReportBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = ReportDataGenerator(seed=7).generate(
            "Продажи", START, END, "Отдел продаж", "Иван Петров"
        )
        self.layout = ReportBuilder().build(self.report, "Тестовый аналитический вывод.")

    def test_layout_size(self) -> None:
        self.assertEqual(self.layout.data_rows, len(self.report.rows))
        self.assertEqual(self.layout.footer_row, 27 + len(self.report.rows))
        self.assertEqual(len(self.layout.values), self.layout.footer_row)
        for row in self.layout.values:
            self.assertEqual(len(row), 6)

    def test_header_values(self) -> None:
        self.assertEqual(self.layout.values[TITLE_ROW - 1][0], self.report.title)
        self.assertIn("за период", self.layout.values[1][0])
        self.assertEqual(self.layout.values[3][0], "Подразделение:")
        self.assertEqual(self.layout.values[3][1], "Отдел продаж")
        self.assertEqual(self.layout.values[KPI_FIRST_ROW - 1][0], self.report.kpis[0].name)

    def test_table_header_and_data(self) -> None:
        header = self.layout.values[TABLE_HEADER_ROW - 1]
        self.assertEqual(header, self.report.columns)
        first_data_row = self.layout.values[DATA_FIRST_ROW - 1]
        self.assertEqual(first_data_row[0], self.report.rows[0][0])
        self.assertEqual(first_data_row[1], self.report.rows[0][1])

    def test_totals_row_uses_formulas(self) -> None:
        totals = self.layout.values[self.layout.totals_row - 1]
        self.assertEqual(totals[0], "Итого")
        data_last = DATA_FIRST_ROW + self.layout.data_rows - 1
        self.assertEqual(totals[2], f"=SUM(C{DATA_FIRST_ROW}:C{data_last})")
        self.assertEqual(totals[3], f"=SUM(D{DATA_FIRST_ROW}:D{data_last})")

    def test_merges(self) -> None:
        self.assertIn((TITLE_ROW, TITLE_ROW, 1, 6), self.layout.merges)
        self.assertIn(
            (self.layout.analysis_first_row, self.layout.analysis_last_row, 1, 6),
            self.layout.merges,
        )
        self.assertIn((self.layout.footer_row, self.layout.footer_row, 1, 6), self.layout.merges)

    def test_format_requests(self) -> None:
        requests = self.layout.format_requests(sheet_id=123)
        self.assertGreater(len(requests), 30)
        for request in requests:
            self.assertEqual(len(request), 1)
        frozen = requests[0]["updateSheetProperties"]
        self.assertEqual(frozen["properties"]["gridProperties"]["frozenRowCount"], 5)
        self.assertEqual(frozen["properties"]["sheetId"], 123)

    def test_chart_spec(self) -> None:
        spec = self.layout.chart_spec()
        data_last = TABLE_HEADER_ROW + self.layout.data_rows
        self.assertEqual(spec["source_range"], f"A{TABLE_HEADER_ROW}:F{data_last}")
        self.assertEqual(spec["series_column"], self.report.schema.chart_column)
        self.assertEqual(spec["anchor_cell"], "H4")

    def test_analysis_text_written(self) -> None:
        self.assertEqual(
            self.layout.values[self.layout.analysis_first_row - 1][0],
            "Тестовый аналитический вывод.",
        )

    def test_empty_ai_text_gets_placeholder(self) -> None:
        layout = ReportBuilder().build(self.report, "   ")
        self.assertTrue(layout.values[layout.analysis_first_row - 1][0])

    def test_all_report_types_build(self) -> None:
        for report_type in ("Продажи", "Финансы", "Склад", "Маркетинг", "HR"):
            with self.subTest(report_type=report_type):
                report = ReportDataGenerator(seed=3).generate(report_type, START, END)
                layout = ReportBuilder().build(report, "Вывод.")
                self.assertGreater(len(layout.values), 30)
                self.assertGreater(len(layout.format_requests(1)), 30)


if __name__ == "__main__":
    unittest.main()
