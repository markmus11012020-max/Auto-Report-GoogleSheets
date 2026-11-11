"""Интеграционные тесты GoogleSheetsClient с подменой сетевого слоя."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google_sheets import GoogleSheetsClient


class FakeRequest:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeValuesAPI:
    def __init__(self, state):
        self.state = state

    def get(self, **kwargs):
        self.state["last_read"] = kwargs
        return FakeRequest({"values": self.state["values"]})

    def update(self, **kwargs):
        self.state["last_update"] = kwargs
        return FakeRequest({"updatedRows": len(kwargs["body"]["values"])})

    def append(self, **kwargs):
        self.state["last_append"] = kwargs
        return FakeRequest({"updates": {"updatedRows": len(kwargs["body"]["values"])}})

    def clear(self, **kwargs):
        self.state["last_clear"] = kwargs
        return FakeRequest({})


class FakeSpreadsheetsAPI:
    def __init__(self, state):
        self.state = state

    def get(self, **kwargs):
        return FakeRequest(self.state["metadata"])

    def batchUpdate(self, **kwargs):
        body = kwargs["body"]
        self.state["batches"].append(body)
        replies = []
        for request in body.get("requests", []):
            if "addSheet" in request:
                properties = request["addSheet"]["properties"]
                sheet = {
                    "properties": {
                        "title": properties["title"],
                        "sheetId": self.state["next_sheet_id"],
                        "index": len(self.state["metadata"]["sheets"]),
                    }
                }
                self.state["next_sheet_id"] += 1
                self.state["metadata"]["sheets"].append(sheet)
                replies.append({"addSheet": {"properties": sheet["properties"]}})
            elif "deleteSheet" in request:
                sheet_id = request["deleteSheet"]["sheetId"]
                self.state["metadata"]["sheets"] = [
                    sheet
                    for sheet in self.state["metadata"]["sheets"]
                    if sheet["properties"]["sheetId"] != sheet_id
                ]
                replies.append({})
        return FakeRequest({"replies": replies})

    def values(self):
        return FakeValuesAPI(self.state)


class FakeService:
    def __init__(self, state):
        self.state = state

    def spreadsheets(self):
        return FakeSpreadsheetsAPI(self.state)


class GoogleSheetsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials = Path(self.temp_dir.name) / "service_account.json"
        self.credentials.write_text("{}", encoding="utf-8")

        self.state = {
            "metadata": {
                "properties": {"title": "Тестовая таблица"},
                "sheets": [
                    {
                        "properties": {
                            "title": "Лист1",
                            "sheetId": 0,
                            "index": 0,
                        }
                    }
                ],
            },
            "values": [["A", "B"], ["1", "2"]],
            "batches": [],
            "next_sheet_id": 10,
            "last_read": None,
            "last_update": None,
            "last_append": None,
            "last_clear": None,
        }
        self.service = FakeService(self.state)
        self.client = GoogleSheetsClient(self.credentials, "spreadsheet-id")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _connect(self) -> None:
        with patch(
            "google_sheets.service_account.Credentials.from_service_account_file",
            return_value=object(),
        ), patch("google_sheets.build", return_value=self.service):
            self.client.connect()

    def test_connect_and_metadata(self) -> None:
        self._connect()
        self.assertEqual(self.client.list_sheets(), ["Лист1"])
        info = self.client.get_spreadsheet_info()
        self.assertEqual(info["title"], "Тестовая таблица")
        self.assertIn("spreadsheet-id", info["url"])
        self.assertEqual(self.client.get_sheet_id("Лист1"), 0)

    def test_read_all(self) -> None:
        self._connect()
        values = self.client.read_all()
        self.assertEqual(values, [["A", "B"], ["1", "2"]])
        self.assertEqual(self.state["last_read"]["range"], "'Лист1'")

    def test_update_and_append(self) -> None:
        self._connect()
        updated = self.client.update_range("'Лист1'!A1", [[1, 2], [3, 4]])
        self.assertEqual(updated, 2)
        self.assertEqual(self.state["last_update"]["valueInputOption"], "USER_ENTERED")

        appended = self.client.append_rows("Лист1", [[5, 6]])
        self.assertEqual(appended, 1)
        self.assertEqual(self.state["last_append"]["insertDataOption"], "INSERT_ROWS")

    def test_create_and_delete_sheet(self) -> None:
        self._connect()
        sheet_id = self.client.create_sheet("Новый")
        self.assertEqual(sheet_id, 10)
        self.assertIn("Новый", self.client.list_sheets())

        self.client.delete_sheet("Новый")
        self.assertNotIn("Новый", self.client.list_sheets())

    def test_batch_format(self) -> None:
        self._connect()
        requests = [{"repeatCell": {"range": {"sheetId": 0}}}]
        self.client.batch_format(0, requests)
        self.assertEqual(self.state["batches"][-1]["requests"], requests)

    def test_add_chart(self) -> None:
        self._connect()
        self.client.add_chart(0, "A15:F45", series_column=3, title="Диаграмма")
        request = self.state["batches"][-1]["requests"][0]
        chart = request["addChart"]["chart"]
        basic = chart["spec"]["basicChart"]
        self.assertEqual(basic["chartType"], "COLUMN")
        self.assertEqual(basic["headerCount"], 1)
        self.assertEqual(basic["domains"][0]["domain"]["sourceRange"]["sources"][0]["startColumnIndex"], 0)
        self.assertEqual(basic["series"][0]["series"]["sourceRange"]["sources"][0]["startColumnIndex"], 3)
        self.assertEqual(chart["position"]["overlayPosition"]["anchorCell"]["rowIndex"], 3)
        self.assertEqual(chart["position"]["overlayPosition"]["anchorCell"]["columnIndex"], 7)

    def test_merge_and_widths(self) -> None:
        self._connect()
        self.client.merge_cells(0, "A1:F1")
        self.assertIn("mergeCells", self.state["batches"][-1]["requests"][0])

        self.client.set_column_widths(0, [100, 200])
        dimensions = self.state["batches"][-1]["requests"]
        self.assertEqual(len(dimensions), 2)
        self.assertEqual(
            dimensions[1]["updateDimensionProperties"]["properties"]["pixelSize"], 200
        )

    def test_clear_and_delete_rows(self) -> None:
        self._connect()
        self.client.clear_range("'Лист1'!A1:B2")
        self.assertEqual(self.state["last_clear"]["range"], "'Лист1'!A1:B2")

        self.client.delete_rows("Лист1", 5, 2)
        request = self.state["batches"][-1]["requests"][0]["deleteDimension"]
        self.assertEqual(request["range"]["startIndex"], 5)
        self.assertEqual(request["range"]["endIndex"], 7)


if __name__ == "__main__":
    unittest.main()
