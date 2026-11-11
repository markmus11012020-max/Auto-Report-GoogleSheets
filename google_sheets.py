"""Модуль работы с Google Таблицами через Google Sheets API v4.

Класс :class:`GoogleSheetsClient` инкапсулирует авторизацию сервисного аккаунта,
CRUD-операции над листами и ячейками, пакетное форматирование и построение диаграмм.

Модуль не зависит от tkinter и может использоваться в любом другом приложении.

Точка входа для самопроверки::

    python google_sheets.py
    python google_sheets.py --sheet "Продажи" --max-rows 50
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Settings, get_settings, get_logger, setup_logging

LOGGER = get_logger("sheets")

SHEETS_API = "sheets"
SHEETS_VERSION = "v4"
CELL_RANGE_RE = re.compile(r"^([A-Za-z]+)(\d+)?(?::([A-Za-z]+)(\d+)?)?$")


class SheetsError(Exception):
    """Базовое исключение модуля."""


class SheetsConnectionError(SheetsError):
    """Не удалось подключиться к Google Таблице."""


class SheetsOperationError(SheetsError):
    """Операция с Google Таблицей завершилась ошибкой."""


def column_to_index(letters: str) -> int:
    """Преобразовать буквы столбца (A, B, AA) в 0-based индекс."""

    result = 0
    for char in letters.upper():
        if not "A" <= char <= "Z":
            raise ValueError(f"Некорректное обозначение столбца: {letters!r}")
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def index_to_column(index: int) -> str:
    """Преобразовать 0-based индекс столбца в буквы."""

    if index < 0:
        raise ValueError("Индекс столбца не может быть отрицательным")
    result = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def cell_to_rowcol(cell: str) -> tuple[int, int]:
    """Преобразовать адрес ячейки (H4) в 0-based (row, column)."""

    match = re.fullmatch(r"([A-Za-z]+)(\d+)", cell.strip())
    if not match:
        raise ValueError(f"Некорректный адрес ячейки: {cell!r}")
    return int(match.group(2)) - 1, column_to_index(match.group(1))


def quote_sheet(title: str) -> str:
    """Заключить имя листа в кавычки для A1-нотации."""

    return "'" + title.replace("'", "''") + "'"


class GoogleSheetsClient:
    """Клиент Google Sheets API с минимально необходимыми правами."""

    def __init__(
        self,
        credentials_path: str | Path,
        spreadsheet_id: str,
        scopes: Sequence[str] | None = None,
    ) -> None:
        self.credentials_path = Path(credentials_path)
        self.spreadsheet_id = (spreadsheet_id or "").strip()
        self.scopes = list(
            scopes or ["https://www.googleapis.com/auth/spreadsheets"]
        )

        self._service: Any = None
        self._metadata: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Подключение
    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, settings: Settings) -> "GoogleSheetsClient":
        return cls(
            credentials_path=settings.credentials_file,
            spreadsheet_id=settings.spreadsheet_id,
            scopes=settings.scopes,
        )

    def connect(self) -> "GoogleSheetsClient":
        """Авторизоваться и проверить доступ к таблице."""

        if not self.spreadsheet_id:
            raise SheetsConnectionError("Не задан SPREADSHEET_ID")
        if not self.credentials_path.exists():
            raise SheetsConnectionError(
                f"Не найден файл ключа сервисного аккаунта: {self.credentials_path}"
            )

        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(self.credentials_path), scopes=self.scopes
            )
        except Exception as exc:  # noqa: BLE001 - нужен понятный текст ошибки
            raise SheetsConnectionError(
                f"Не удалось прочитать JSON-ключ {self.credentials_path.name}: {exc}"
            ) from exc

        try:
            self._service = build(
                SHEETS_API, SHEETS_VERSION, credentials=credentials, cache_discovery=False
            )
            self._metadata = (
                self._service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
        except HttpError as exc:
            raise SheetsConnectionError(self._describe_http_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise SheetsConnectionError(
                "Не удалось подключиться к Google Sheets API. "
                f"Проверьте интернет-соединение. Детали: {exc}"
            ) from exc

        LOGGER.info("Подключение к таблице %s установлено", self.spreadsheet_id)
        return self

    @property
    def service(self) -> Any:
        if self._service is None:
            raise SheetsConnectionError("Сначала вызовите connect()")
        return self._service

    def _refresh_metadata(self) -> dict[str, Any]:
        try:
            self._metadata = (
                self.service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc
        return self._metadata or {}

    def metadata(self) -> dict[str, Any]:
        return self._metadata or self._refresh_metadata()

    def get_spreadsheet_info(self) -> dict[str, Any]:
        """Вернуть название, ссылку и список листов."""

        meta = self.metadata()
        return {
            "title": meta.get("properties", {}).get("title", ""),
            "url": self.get_url(),
            "sheets": [
                {
                    "title": sheet.get("properties", {}).get("title", ""),
                    "sheet_id": sheet.get("properties", {}).get("sheetId"),
                    "index": sheet.get("properties", {}).get("index"),
                }
                for sheet in meta.get("sheets", [])
            ],
        }

    def get_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"

    def sheet_url(self, title: str) -> str:
        sheet_id = self.get_sheet_id(title)
        return f"{self.get_url()}#gid={sheet_id}"

    # ------------------------------------------------------------------
    # Листы
    # ------------------------------------------------------------------
    def list_sheets(self) -> list[str]:
        meta = self.metadata()
        return [
            sheet.get("properties", {}).get("title", "")
            for sheet in meta.get("sheets", [])
        ]

    def get_sheet_id(self, title: str) -> int:
        for sheet in self.metadata().get("sheets", []):
            properties = sheet.get("properties", {})
            if properties.get("title") == title:
                return int(properties.get("sheetId", 0))
        raise SheetsOperationError(f"Лист {title!r} не найден")

    def sheet_exists(self, title: str) -> bool:
        return title in self.list_sheets()

    def _first_sheet_title(self) -> str:
        titles = self.list_sheets()
        if not titles:
            raise SheetsOperationError("В таблице нет ни одного листа")
        return titles[0]

    def create_sheet(self, title: str) -> int:
        """Создать лист и вернуть его sheetId."""

        title = (title or "").strip()
        if not title:
            raise SheetsOperationError("Название листа не может быть пустым")
        if len(title) > 100:
            raise SheetsOperationError("Название листа не должно превышать 100 символов")
        if self.sheet_exists(title):
            raise SheetsOperationError(f"Лист {title!r} уже существует")

        body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
        reply = self._batch_update_raw(body)
        self._refresh_metadata()
        sheet_id = int(reply["replies"][0]["addSheet"]["properties"]["sheetId"])
        LOGGER.info("Создан лист %r (sheetId=%s)", title, sheet_id)
        return sheet_id

    def delete_sheet(self, title: str) -> None:
        sheet_id = self.get_sheet_id(title)
        self._batch_update_raw(
            {"requests": [{"deleteSheet": {"sheetId": sheet_id}}]}
        )
        self._refresh_metadata()
        LOGGER.info("Удалён лист %r", title)

    # ------------------------------------------------------------------
    # Чтение и запись
    # ------------------------------------------------------------------
    def read_all(self, sheet: str | None = None) -> list[list[str]]:
        """Прочитать все ячейки листа (по умолчанию — первого листа)."""

        title = sheet or self._first_sheet_title()
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=quote_sheet(title))
                .execute()
            )
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc
        return result.get("values", [])

    def read_workbook(self) -> dict[str, list[list[str]]]:
        """Прочитать все листы книги."""

        return {title: self.read_all(title) for title in self.list_sheets()}

    def read_range(self, a1_range: str) -> list[list[str]]:
        """Прочитать произвольный диапазон в A1-нотации."""

        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=a1_range)
                .execute()
            )
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc
        return result.get("values", [])

    def append_rows(self, sheet: str, rows: Iterable[Sequence[Any]]) -> int:
        """Добавить строки в конец листа. Возвращает число добавленных строк."""

        values = [list(row) for row in rows]
        if not values:
            return 0
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range=quote_sheet(sheet),
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": values},
                )
                .execute()
            )
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc
        updated = result.get("updates", {})
        LOGGER.info("Добавлено строк: %s", updated.get("updatedRows", len(values)))
        return int(updated.get("updatedRows", len(values)))

    def update_range(
        self,
        a1_range: str,
        values: Sequence[Sequence[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> int:
        """Записать значения в диапазон."""

        body = {"values": [list(row) for row in values]}
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.spreadsheet_id,
                    range=a1_range,
                    valueInputOption=value_input_option,
                    body=body,
                )
                .execute()
            )
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc
        return int(result.get("updatedRows", 0))

    def clear_range(self, a1_range: str) -> None:
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id, range=a1_range, body={}
            ).execute()
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc

    def delete_rows(self, sheet: str, start_index: int, count: int) -> None:
        """Удалить строки листа. start_index — 0-based."""

        if count <= 0:
            return
        sheet_id = self.get_sheet_id(sheet)
        request = {
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_index,
                    "endIndex": start_index + count,
                }
            }
        }
        self.batch_update([request])

    # ------------------------------------------------------------------
    # Форматирование
    # ------------------------------------------------------------------
    def _batch_update_raw(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            return (
                self.service.spreadsheets()
                .batchUpdate(spreadsheetId=self.spreadsheet_id, body=body)
                .execute()
            )
        except HttpError as exc:
            raise SheetsOperationError(self._describe_http_error(exc)) from exc

    def batch_update(self, requests: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not requests:
            return {}
        return self._batch_update_raw({"requests": list(requests)})

    def batch_format(self, sheet_id: int, requests: Sequence[dict[str, Any]]) -> None:
        """Применить пакет запросов форматирования (sheetId уже учтён в запросах)."""

        if not requests:
            return
        self.batch_update(requests)
        LOGGER.info("Применено запросов форматирования: %s (sheetId=%s)", len(requests), sheet_id)

    def merge_cells(self, sheet_id: int, a1_range: str) -> None:
        grid = self.a1_to_grid_range(a1_range, sheet_id)
        self.batch_update([{"mergeCells": {"range": grid, "mergeType": "MERGE_ALL"}}])

    def set_column_widths(self, sheet_id: int, widths: Sequence[int]) -> None:
        requests = []
        for index, width in enumerate(widths):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": index,
                            "endIndex": index + 1,
                        },
                        "properties": {"pixelSize": int(width)},
                        "fields": "pixelSize",
                    }
                }
            )
        self.batch_update(requests)

    def set_row_heights(self, sheet_id: int, heights: dict[int, int]) -> None:
        """heights: {номер_строки_1based: высота_px}."""

        requests = []
        for row, height in sorted(heights.items()):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row - 1,
                            "endIndex": row,
                        },
                        "properties": {"pixelSize": int(height)},
                        "fields": "pixelSize",
                    }
                }
            )
        self.batch_update(requests)

    # ------------------------------------------------------------------
    # Диаграммы
    # ------------------------------------------------------------------
    def add_chart(
        self,
        sheet_id: int,
        source_range: str,
        anchor_cell: str = "H4",
        title: str = "Диаграмма",
        series_column: int = 0,
        header_rows: int = 1,
        width_px: int = 600,
        height_px: int = 360,
    ) -> None:
        """Добавить столбчатую диаграмму по диапазону (первый столбец — категории)."""

        grid = self.a1_to_grid_range(source_range, sheet_id)
        anchor_row, anchor_column = cell_to_rowcol(anchor_cell)

        start_row = grid["startRowIndex"]
        end_row = grid["endRowIndex"]
        series_col = grid["startColumnIndex"] + series_column

        domain = {
            "domain": {
                "sourceRange": {
                    "sources": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": grid["startColumnIndex"],
                            "endColumnIndex": grid["startColumnIndex"] + 1,
                        }
                    ]
                }
            }
        }
        series = {
            "series": {
                "sourceRange": {
                    "sources": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": series_col,
                            "endColumnIndex": series_col + 1,
                        }
                    ]
                }
            },
            "targetAxis": "LEFT_AXIS",
        }

        chart = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": title,
                        "basicChart": {
                            "chartType": "COLUMN",
                            "legendPosition": "BOTTOM_LEGEND",
                            "headerCount": header_rows,
                            "domains": [domain],
                            "series": [series],
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": sheet_id,
                                "rowIndex": anchor_row,
                                "columnIndex": anchor_column,
                            },
                            "widthPixels": width_px,
                            "heightPixels": height_px,
                        }
                    },
                }
            }
        }
        self.batch_update([chart])
        LOGGER.info("Диаграмма добавлена на лист sheetId=%s", sheet_id)

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------
    @staticmethod
    def a1_to_grid_range(a1_range: str, sheet_id: int) -> dict[str, int]:
        """Преобразовать A1-диапазон (A1:F10) в GridRange."""

        value = (a1_range or "").strip()
        if "!" in value:
            value = value.split("!", 1)[1]
        match = CELL_RANGE_RE.fullmatch(value)
        if not match:
            raise ValueError(f"Некорректный диапазон: {a1_range!r}")

        start_col_letters, start_row, end_col_letters, end_row = match.groups()
        start_col = column_to_index(start_col_letters)
        start_row_index = int(start_row) - 1 if start_row else 0

        if end_col_letters:
            end_col = column_to_index(end_col_letters) + 1
        else:
            end_col = start_col + 1

        if end_row:
            end_row_index = int(end_row)
        elif start_row:
            end_row_index = int(start_row)
        else:
            raise ValueError(
                f"Для диапазона {a1_range!r} укажите конечную строку (например, A1:F10)"
            )

        return {
            "sheetId": sheet_id,
            "startRowIndex": start_row_index,
            "endRowIndex": end_row_index,
            "startColumnIndex": start_col,
            "endColumnIndex": end_col,
        }

    @staticmethod
    def _describe_http_error(exc: HttpError) -> str:
        status = getattr(exc.resp, "status", None)
        details = ""
        try:
            details = exc.content.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            details = str(exc)

        if status == 403:
            return (
                "Доступ запрещён. Проверьте, что таблица открыта сервисному "
                "аккаунту (роль Editor) и Google Sheets API включён в проекте. "
                f"Детали: {details}"
            )
        if status == 404:
            return (
                "Таблица не найдена. Проверьте SPREADSHEET_ID. "
                f"Детали: {details}"
            )
        if status == 429:
            return "Превышена квота Google Sheets API. Повторите попытку позже."
        return f"Ошибка Google Sheets API (HTTP {status}): {details}"


# ----------------------------------------------------------------------
# Точка входа для самопроверки
# ----------------------------------------------------------------------
def format_table(values: Sequence[Sequence[Any]], max_rows: int | None = None) -> str:
    """Сформировать текстовую таблицу для консоли."""

    if not values:
        return "(лист пуст)"

    rows = [list(row) for row in values]
    if max_rows is not None:
        rows = rows[:max_rows]

    width = max(len(row) for row in rows)
    normalized = [
        [str(cell).replace("\n", " ") if cell is not None else "" for cell in row]
        + [""] * (width - len(row))
        for row in rows
    ]
    widths = [max(len(row[index]) for row in normalized) for index in range(width)]
    separator = "-+-".join("-" * value for value in widths)

    lines = []
    for index, row in enumerate(normalized):
        lines.append(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if index == 0:
            lines.append(separator)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(
        description="Чтение Google Таблицы через сервисный аккаунт (самопроверка модуля)."
    )
    parser.add_argument("--sheet", help="Имя листа. По умолчанию читаются все листы.")
    parser.add_argument(
        "--max-rows", type=int, default=100, help="Сколько строк печатать (по умолчанию 100)."
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings)

    problems = settings.google_problems()
    if problems:
        for problem in problems:
            print(f"[ОШИБКА] {problem}", file=sys.stderr)
        print(
            "\nЗаполните .env по образцу .env.example и положите ключ сервисного "
            "аккаунта в корень проекта.",
            file=sys.stderr,
        )
        return 1

    client = GoogleSheetsClient.from_settings(settings)
    try:
        client.connect()
        info = client.get_spreadsheet_info()
        print(f"Таблица: {info['title']}")
        print(f"Ссылка:  {info['url']}")
        print(f"Листов:  {len(info['sheets'])}")

        titles = [args.sheet] if args.sheet else client.list_sheets()
        for title in titles:
            values = client.read_all(title)
            rows = len(values)
            columns = max((len(row) for row in values), default=0)
            print(f"\n=== Лист: {title} ===")
            print(f"Строк: {rows}, столбцов: {columns}")
            print(format_table(values, args.max_rows))
            if args.max_rows and rows > args.max_rows:
                print(f"... показаны первые {args.max_rows} строк из {rows}")
        return 0
    except SheetsError as exc:
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        LOGGER.error("Самопроверка завершилась ошибкой: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
