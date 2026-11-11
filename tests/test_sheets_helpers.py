"""Тесты вспомогательных функций модуля Google Sheets."""

from __future__ import annotations

import unittest

from google_sheets import (
    GoogleSheetsClient,
    column_to_index,
    format_table,
    index_to_column,
    quote_sheet,
)


class ColumnTests(unittest.TestCase):
    def test_column_conversion(self) -> None:
        self.assertEqual(column_to_index("A"), 0)
        self.assertEqual(column_to_index("F"), 5)
        self.assertEqual(column_to_index("AA"), 26)
        self.assertEqual(index_to_column(0), "A")
        self.assertEqual(index_to_column(25), "Z")
        self.assertEqual(index_to_column(26), "AA")

    def test_round_trip(self) -> None:
        for index in range(0, 200):
            self.assertEqual(column_to_index(index_to_column(index)), index)

    def test_invalid_column(self) -> None:
        with self.assertRaises(ValueError):
            column_to_index("1A")


class GridRangeTests(unittest.TestCase):
    def test_full_range(self) -> None:
        grid = GoogleSheetsClient.a1_to_grid_range("A1:F10", 5)
        self.assertEqual(
            grid,
            {
                "sheetId": 5,
                "startRowIndex": 0,
                "endRowIndex": 10,
                "startColumnIndex": 0,
                "endColumnIndex": 6,
            },
        )

    def test_sheet_prefix(self) -> None:
        grid = GoogleSheetsClient.a1_to_grid_range("'Мой лист'!B2:D4", 7)
        self.assertEqual(grid["startRowIndex"], 1)
        self.assertEqual(grid["endRowIndex"], 4)
        self.assertEqual(grid["startColumnIndex"], 1)
        self.assertEqual(grid["endColumnIndex"], 4)

    def test_single_column(self) -> None:
        grid = GoogleSheetsClient.a1_to_grid_range("C1:C3", 1)
        self.assertEqual(grid["startColumnIndex"], 2)
        self.assertEqual(grid["endColumnIndex"], 3)

    def test_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            GoogleSheetsClient.a1_to_grid_range("A", 1)


class MiscTests(unittest.TestCase):
    def test_quote_sheet(self) -> None:
        self.assertEqual(quote_sheet("Продажи"), "'Продажи'")
        self.assertEqual(quote_sheet("It's"), "'It''s'")

    def test_format_table(self) -> None:
        text = format_table([["A", "B"], ["1", "22"]])
        self.assertIn("A | B", text)
        self.assertIn("--+---", text)
        self.assertIn("1 | 22", text)

    def test_format_empty_table(self) -> None:
        self.assertEqual(format_table([]), "(лист пуст)")


if __name__ == "__main__":
    unittest.main()
