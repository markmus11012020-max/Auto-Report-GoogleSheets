"""Компоновка отчёта: значения ячеек, объединения, форматирование и диаграмма.

Модуль не зависит от tkinter и Google API: он формирует модель листа,
которую приложение записывает через :class:`google_sheets.GoogleSheetsClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from report_data import Column, ReportData

COLUMNS = 6

TITLE_ROW = 1
SUBTITLE_ROW = 2
META_ROW = 4
KPI_SECTION_ROW = 6
KPI_HEADER_ROW = 7
KPI_FIRST_ROW = 8
KPI_LAST_ROW = 12
DETAIL_SECTION_ROW = 14
TABLE_HEADER_ROW = 15
DATA_FIRST_ROW = 16


def _rgb(hex_color: str) -> dict[str, float]:
    value = hex_color.lstrip("#")
    return {
        "red": int(value[0:2], 16) / 255,
        "green": int(value[2:4], 16) / 255,
        "blue": int(value[4:6], 16) / 255,
    }


DARK = "#1F3864"
ACCENT = "#2E75B6"
LIGHT = "#D9E2F3"
ALT_ROW = "#F2F6FC"
BORDER = "#BFBFBF"
TEXT = "#262626"
MUTED = "#595959"
POSITIVE = "#375623"
NEGATIVE = "#C00000"
ANALYSIS_FILL = "#FAFBFD"


def _text_format(
    size: int = 10,
    bold: bool = False,
    italic: bool = False,
    color: str = TEXT,
    font: str = "Calibri",
) -> dict[str, Any]:
    return {
        "textFormat": {
            "fontFamily": font,
            "fontSize": size,
            "bold": bold,
            "italic": italic,
            "foregroundColor": _rgb(color),
        }
    }


def _borders(color: str = BORDER) -> dict[str, Any]:
    side = {"style": "SOLID", "color": _rgb(color)}
    return {"top": dict(side), "bottom": dict(side), "left": dict(side), "right": dict(side)}


NUMBER_FORMATS: dict[str, dict[str, str]] = {
    "date": {"type": "DATE", "pattern": "dd.mm.yyyy"},
    "currency": {"type": "NUMBER", "pattern": '#,##0.00" ₽"'},
    "percent": {"type": "PERCENT", "pattern": "0.0%"},
    "integer": {"type": "NUMBER", "pattern": "#,##0"},
}


def _grid(sheet_id: int, row1: int, row2: int, col1: int = 1, col2: int = COLUMNS) -> dict[str, int]:
    """GridRange по 1-based включительным координатам."""

    return {
        "sheetId": sheet_id,
        "startRowIndex": row1 - 1,
        "endRowIndex": row2,
        "startColumnIndex": col1 - 1,
        "endColumnIndex": col2,
    }


def _repeat(
    sheet_id: int,
    row1: int,
    row2: int,
    col1: int,
    col2: int,
    cell_format: dict[str, Any],
    fields: str = "userEnteredFormat",
) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": _grid(sheet_id, row1, row2, col1, col2),
            "cell": {"userEnteredFormat": cell_format},
            "fields": fields,
        }
    }


def _row_height(sheet_id: int, row: int, height: int) -> dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": row - 1,
                "endIndex": row,
            },
            "properties": {"pixelSize": height},
            "fields": "pixelSize",
        }
    }


def _row_range_height(sheet_id: int, row1: int, row2: int, height: int) -> dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": row1 - 1,
                "endIndex": row2,
            },
            "properties": {"pixelSize": height},
            "fields": "pixelSize",
        }
    }


def _column_width(sheet_id: int, column: int, width: int) -> dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": column - 1,
                "endIndex": column,
            },
            "properties": {"pixelSize": width},
            "fields": "pixelSize",
        }
    }


@dataclass
class ReportLayout:
    """Готовая модель листа отчёта."""

    report: ReportData
    ai_text: str
    values: list[list[Any]] = field(default_factory=list)
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)

    data_rows: int = 0
    totals_row: int = 0
    analysis_section_row: int = 0
    analysis_first_row: int = 0
    analysis_last_row: int = 0
    footer_row: int = 0

    def __post_init__(self) -> None:
        self.data_rows = len(self.report.rows)
        self.totals_row = DATA_FIRST_ROW + self.data_rows
        self.analysis_section_row = self.totals_row + 2
        self.analysis_first_row = self.analysis_section_row + 1
        self.analysis_last_row = self.analysis_first_row + 7
        self.footer_row = self.analysis_last_row + 1
        self.merges = [
            (TITLE_ROW, TITLE_ROW, 1, COLUMNS),
            (SUBTITLE_ROW, SUBTITLE_ROW, 1, COLUMNS),
            (KPI_SECTION_ROW, KPI_SECTION_ROW, 1, COLUMNS),
            (DETAIL_SECTION_ROW, DETAIL_SECTION_ROW, 1, COLUMNS),
            (self.analysis_section_row, self.analysis_section_row, 1, COLUMNS),
            (self.analysis_first_row, self.analysis_last_row, 1, COLUMNS),
            (self.footer_row, self.footer_row, 1, COLUMNS),
        ]
        self.values = self._build_values()

    # ------------------------------------------------------------------
    # Значения
    # ------------------------------------------------------------------
    def _build_values(self) -> list[list[Any]]:
        grid = [[""] * COLUMNS for _ in range(self.footer_row)]
        report = self.report

        def put(row: int, column: int, value: Any) -> None:
            grid[row - 1][column - 1] = value

        put(TITLE_ROW, 1, report.title)
        put(SUBTITLE_ROW, 1, report.period_label)

        put(META_ROW, 1, "Подразделение:")
        put(META_ROW, 2, report.department)
        put(META_ROW, 3, "Автор:")
        put(META_ROW, 4, report.author or "—")
        put(META_ROW, 5, "Дата формирования:")
        put(META_ROW, 6, report.generated_at.strftime("%d.%m.%Y %H:%M"))

        put(KPI_SECTION_ROW, 1, "Ключевые показатели")
        for column, title in enumerate(
            ("Показатель", "Значение", "Ед. изм.", "Изменение"), start=1
        ):
            put(KPI_HEADER_ROW, column, title)

        for index, kpi in enumerate(report.kpis[:5]):
            row = KPI_FIRST_ROW + index
            put(row, 1, kpi.name)
            put(row, 2, round(float(kpi.value), 2))
            put(row, 3, kpi.unit)
            put(row, 4, round(kpi.change_pct / 100, 5))

        put(DETAIL_SECTION_ROW, 1, "Детализация")
        for column, title in enumerate(report.columns, start=1):
            put(TABLE_HEADER_ROW, column, title)

        for row_index, row_values in enumerate(report.rows):
            row = DATA_FIRST_ROW + row_index
            for column, value in enumerate(row_values, start=1):
                put(row, column, value)

        put(self.totals_row, 1, "Итого")
        data_last = DATA_FIRST_ROW + self.data_rows - 1
        for column, (kind, total) in enumerate(zip(report.schema.total_kinds, report.totals), start=1):
            if kind == "sum":
                letter = _column_letter(column)
                put(self.totals_row, column, f"=SUM({letter}{DATA_FIRST_ROW}:{letter}{data_last})")
            elif kind == "value" and total != "":
                put(self.totals_row, column, total)

        put(self.analysis_section_row, 1, "Аналитический вывод")
        put(self.analysis_first_row, 1, self.ai_text)

        seed_note = f" seed={self.report.seed}." if self.report.seed is not None else ""
        put(
            self.footer_row,
            1,
            "Отчёт сформирован автоматически "
            f"{report.generated_at:%d.%m.%Y %H:%M}. "
            f"Источник данных — симулятор Excel Factory.{seed_note}",
        )
        return grid

    # ------------------------------------------------------------------
    # Форматирование
    # ------------------------------------------------------------------
    def format_requests(self, sheet_id: int) -> list[dict[str, Any]]:
        requests: list[dict[str, Any]] = []

        # Закрепление строк.
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 5},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )

        # Ширины столбцов из схемы отчёта.
        for index, column in enumerate(self.report.schema.columns, start=1):
            requests.append(_column_width(sheet_id, index, column.width_px))

        # Высоты строк.
        for row, height in (
            (TITLE_ROW, 34),
            (SUBTITLE_ROW, 20),
            (3, 6),
            (5, 6),
            (KPI_SECTION_ROW, 24),
            (KPI_HEADER_ROW, 24),
            (13, 6),
            (DETAIL_SECTION_ROW, 24),
            (TABLE_HEADER_ROW, 28),
            (self.analysis_section_row, 24),
            (self.totals_row, 22),
            (self.totals_row + 1, 6),
            (self.footer_row, 18),
        ):
            requests.append(_row_height(sheet_id, row, height))
        if self.data_rows:
            requests.append(
                _row_range_height(sheet_id, DATA_FIRST_ROW, DATA_FIRST_ROW + self.data_rows - 1, 20)
            )
        requests.append(
            _row_range_height(sheet_id, self.analysis_first_row, self.analysis_last_row, 22)
        )

        # Объединения.
        for row1, row2, col1, col2 in self.merges:
            requests.append(
                {"mergeCells": {"range": _grid(sheet_id, row1, row2, col1, col2), "mergeType": "MERGE_ALL"}}
            )

        # Заголовок.
        requests.append(
            _repeat(
                sheet_id,
                TITLE_ROW,
                TITLE_ROW,
                1,
                COLUMNS,
                {
                    "backgroundColor": _rgb(DARK),
                    **_text_format(size=14, bold=True, color="#FFFFFF"),
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP",
                },
            )
        )
        # Подзаголовок с периодом.
        requests.append(
            _repeat(
                sheet_id,
                SUBTITLE_ROW,
                SUBTITLE_ROW,
                1,
                COLUMNS,
                {
                    **_text_format(size=11, italic=True, color=MUTED),
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                },
            )
        )
        # Метаданные.
        requests.append(
            _repeat(
                sheet_id,
                META_ROW,
                META_ROW,
                1,
                COLUMNS,
                {
                    **_text_format(size=10),
                    "verticalAlignment": "MIDDLE",
                },
            )
        )
        for column in (1, 3, 5):
            requests.append(
                _repeat(
                    sheet_id,
                    META_ROW,
                    META_ROW,
                    column,
                    column,
                    _text_format(size=10, bold=True),
                    "userEnteredFormat.textFormat",
                )
            )

        # Заголовки блоков.
        for row in (KPI_SECTION_ROW, DETAIL_SECTION_ROW, self.analysis_section_row):
            requests.append(
                _repeat(
                    sheet_id,
                    row,
                    row,
                    1,
                    COLUMNS,
                    {
                        "backgroundColor": _rgb(ACCENT),
                        **_text_format(size=12, bold=True, color="#FFFFFF"),
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE",
                        "padding": {"left": 8},
                    },
                )
            )

        # Блок KPI.
        requests.append(
            _repeat(
                sheet_id,
                KPI_HEADER_ROW,
                KPI_HEADER_ROW,
                1,
                4,
                {
                    "backgroundColor": _rgb(LIGHT),
                    **_text_format(size=10, bold=True, color=DARK),
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "borders": _borders(),
                },
            )
        )
        requests.append(
            _repeat(
                sheet_id,
                KPI_FIRST_ROW,
                KPI_LAST_ROW,
                1,
                4,
                {
                    **_text_format(size=10),
                    "verticalAlignment": "MIDDLE",
                    "borders": _borders(),
                    "padding": {"top": 2, "bottom": 2, "left": 6, "right": 6},
                },
                "userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment,"
                "userEnteredFormat.borders,userEnteredFormat.padding",
            )
        )
        # Выравнивание значений KPI.
        requests.append(
            _repeat(
                sheet_id,
                KPI_FIRST_ROW,
                KPI_LAST_ROW,
                2,
                4,
                {"horizontalAlignment": "CENTER"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
        # Числовой формат значений KPI зависит от единицы измерения.
        for index, kpi in enumerate(self.report.kpis[:5]):
            row = KPI_FIRST_ROW + index
            if kpi.unit == "₽":
                fmt = {"type": "NUMBER", "pattern": "#,##0.00"}
            elif kpi.unit == "%":
                fmt = {"type": "NUMBER", "pattern": "0.0"}
            else:
                fmt = {"type": "NUMBER", "pattern": "#,##0"}
            requests.append(
                _repeat(
                    sheet_id,
                    row,
                    row,
                    2,
                    2,
                    {"numberFormat": fmt},
                    "userEnteredFormat.numberFormat",
                )
            )
        # Изменение KPI: знаковый процент.
        requests.append(
            _repeat(
                sheet_id,
                KPI_FIRST_ROW,
                KPI_LAST_ROW,
                4,
                4,
                {"numberFormat": {"type": "PERCENT", "pattern": "+0.0%;-0.0%;0.0%"}},
                "userEnteredFormat.numberFormat",
            )
        )
        # Подсветка отрицательного/положительного изменения.
        requests.append(self._change_conditional_format(sheet_id))

        # Таблица детализации.
        requests.append(
            _repeat(
                sheet_id,
                TABLE_HEADER_ROW,
                TABLE_HEADER_ROW,
                1,
                COLUMNS,
                {
                    "backgroundColor": _rgb(ACCENT),
                    **_text_format(size=10, bold=True, color="#FFFFFF"),
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP",
                    "borders": _borders(),
                },
            )
        )
        data_last = DATA_FIRST_ROW + self.data_rows - 1
        if self.data_rows:
            requests.append(
                _repeat(
                    sheet_id,
                    DATA_FIRST_ROW,
                    data_last,
                    1,
                    COLUMNS,
                    {
                        **_text_format(size=10),
                        "verticalAlignment": "MIDDLE",
                        "borders": _borders(),
                        "padding": {"top": 2, "bottom": 2, "left": 5, "right": 5},
                    },
                    "userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment,"
                    "userEnteredFormat.borders,userEnteredFormat.padding",
                )
            )
            # Выравнивание и числовые форматы по столбцам.
            for index, column in enumerate(self.report.schema.columns, start=1):
                alignment = {
                    "date": "CENTER",
                    "text": "LEFT",
                    "integer": "RIGHT",
                    "currency": "RIGHT",
                    "percent": "CENTER",
                }.get(column.kind, "LEFT")
                requests.append(
                    _repeat(
                        sheet_id,
                        DATA_FIRST_ROW,
                        data_last,
                        index,
                        index,
                        {"horizontalAlignment": alignment},
                        "userEnteredFormat.horizontalAlignment",
                    )
                )
                number_format = NUMBER_FORMATS.get(column.kind)
                if number_format:
                    requests.append(
                        _repeat(
                            sheet_id,
                            DATA_FIRST_ROW,
                            data_last,
                            index,
                            index,
                            {"numberFormat": number_format},
                            "userEnteredFormat.numberFormat",
                        )
                    )
            # Чередование строк.
            for row in range(DATA_FIRST_ROW + 1, data_last + 1, 2):
                requests.append(
                    _repeat(
                        sheet_id,
                        row,
                        row,
                        1,
                        COLUMNS,
                        {"backgroundColor": _rgb(ALT_ROW)},
                        "userEnteredFormat.backgroundColor",
                    )
                )

        # Итоговая строка.
        requests.append(
            _repeat(
                sheet_id,
                self.totals_row,
                self.totals_row,
                1,
                COLUMNS,
                {
                    "backgroundColor": _rgb(LIGHT),
                    **_text_format(size=10, bold=True, color=DARK),
                    "verticalAlignment": "MIDDLE",
                    "borders": _borders(DARK),
                },
            )
        )
        for index, column in enumerate(self.report.schema.columns, start=1):
            number_format = NUMBER_FORMATS.get(column.kind)
            if number_format:
                requests.append(
                    _repeat(
                        sheet_id,
                        self.totals_row,
                        self.totals_row,
                        index,
                        index,
                        {"numberFormat": number_format},
                        "userEnteredFormat.numberFormat",
                    )
                )

        # Блок аналитического вывода.
        requests.append(
            _repeat(
                sheet_id,
                self.analysis_first_row,
                self.analysis_last_row,
                1,
                COLUMNS,
                {
                    "backgroundColor": _rgb(ANALYSIS_FILL),
                    **_text_format(size=10),
                    "horizontalAlignment": "LEFT",
                    "verticalAlignment": "TOP",
                    "wrapStrategy": "WRAP",
                    "borders": _borders(LIGHT),
                    "padding": {"top": 6, "bottom": 6, "left": 8, "right": 8},
                },
            )
        )

        # Подпись.
        requests.append(
            _repeat(
                sheet_id,
                self.footer_row,
                self.footer_row,
                1,
                COLUMNS,
                {
                    **_text_format(size=8, italic=True, color="#808080"),
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                },
            )
        )

        return requests

    def _change_conditional_format(self, sheet_id: int) -> dict[str, Any]:
        grid = _grid(sheet_id, KPI_FIRST_ROW, KPI_LAST_ROW, 4, 4)
        return {
            "addConditionalFormatting": {
                "conditionalFormats": [
                    {
                        "ranges": [grid],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_LESS",
                                "values": [{"userEnteredValue": "0"}],
                            },
                            "format": {"textFormat": {"foregroundColor": _rgb(NEGATIVE)}},
                        },
                    },
                    {
                        "ranges": [grid],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_GREATER",
                                "values": [{"userEnteredValue": "0"}],
                            },
                            "format": {"textFormat": {"foregroundColor": _rgb(POSITIVE)}},
                        },
                    },
                ]
            }
        }

    # ------------------------------------------------------------------
    def chart_spec(self) -> dict[str, Any]:
        return {
            "source_range": f"A{TABLE_HEADER_ROW}:F{TABLE_HEADER_ROW + self.data_rows}",
            "anchor_cell": "H4",
            "title": self.report.schema.chart_title,
            "series_column": self.report.schema.chart_column,
            "header_rows": 1,
            "width_px": 600,
            "height_px": 360,
        }


def _column_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


class ReportBuilder:
    """Собирает модель листа по данным отчёта и тексту вывода."""

    def build(self, report: ReportData, ai_text: str) -> ReportLayout:
        text = (ai_text or "").strip()
        if not text:
            text = "Аналитический вывод не сформирован."
        return ReportLayout(report=report, ai_text=text)
