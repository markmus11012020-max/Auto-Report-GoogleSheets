"""Генератор случайных, но согласованных данных отчётов.

Данные детерминированы при фиксированном seed и содержат:
- строки детализации;
- итоговую строку;
- пять KPI;
- контекст для языковой модели.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

REPORT_SEED_HINT = "seed"


@dataclass(frozen=True)
class Column:
    title: str
    kind: str  # date | text | integer | currency | percent
    width_px: int = 110


@dataclass(frozen=True)
class ReportSchema:
    name: str
    columns: tuple[Column, ...]
    kpi_names: tuple[str, ...]
    chart_column: int
    chart_title: str
    total_kinds: tuple[str, ...]  # sum | value | empty


SALES_CATEGORIES = [
    "Электроника",
    "Бытовая техника",
    "Аксессуары",
    "Офисная техника",
    "Освещение",
    "Климатическая техника",
]

FINANCE_ARTICLES = [
    "Выручка",
    "Себестоимость",
    "Маркетинг",
    "Зарплата",
    "Аренда",
    "Логистика",
    "Прочие расходы",
    "Налоги",
    "Амортизация",
    "Проценты по кредитам",
]

WAREHOUSE_ITEMS = [
    "Ноутбук офисный",
    "Монитор 27″",
    "Клавиатура проводная",
    "Мышь беспроводная",
    "Принтер лазерный",
    "Сканер документов",
    "Кабель HDMI",
    "ИБП 1000 ВА",
    "Жёсткий диск 1 ТБ",
    "Веб-камера Full HD",
    "Кресло офисное",
    "Стол письменный",
]

MARKETING_CHANNELS = [
    "Контекстная реклама",
    "Таргетированная реклама",
    "Email-рассылка",
    "SEO",
    "Социальные сети",
    "Партнёрская программа",
    "YouTube",
    "Telegram",
    "Баннерная реклама",
    "Ретаргетинг",
]

HR_DEPARTMENTS = [
    "Отдел продаж",
    "Финансовый отдел",
    "Склад",
    "Маркетинг",
    "ИТ-отдел",
    "Отдел кадров",
    "Служба поддержки",
    "Логистика",
    "Юридический отдел",
    "Отдел закупок",
    "Аналитика",
    "Администрация",
]

REPORT_SCHEMAS: dict[str, ReportSchema] = {
    "Продажи": ReportSchema(
        name="Продажи",
        columns=(
            Column("Дата", "date", 110),
            Column("Категория", "text", 190),
            Column("Операций", "integer", 100),
            Column("Сумма", "currency", 140),
            Column("Средний чек", "currency", 130),
            Column("Доля", "percent", 100),
        ),
        kpi_names=(
            "Выручка",
            "Количество операций",
            "Средний чек",
            "Конверсия",
            "Прирост к предыдущему периоду",
        ),
        chart_column=3,
        chart_title="Динамика выручки за период",
        total_kinds=("empty", "empty", "sum", "sum", "value", "value"),
    ),
    "Финансы": ReportSchema(
        name="Финансы",
        columns=(
            Column("Статья", "text", 200),
            Column("План", "currency", 140),
            Column("Факт", "currency", 140),
            Column("Отклонение", "currency", 140),
            Column("Выполнение", "percent", 110),
            Column("Комментарий", "text", 180),
        ),
        kpi_names=(
            "Доходы",
            "Расходы",
            "Прибыль",
            "Маржинальность",
            "Отклонение от плана",
        ),
        chart_column=2,
        chart_title="План и факт по статьям",
        total_kinds=("empty", "sum", "sum", "sum", "value", "empty"),
    ),
    "Склад": ReportSchema(
        name="Склад",
        columns=(
            Column("SKU", "text", 110),
            Column("Наименование", "text", 200),
            Column("Остаток", "integer", 100),
            Column("Резерв", "integer", 100),
            Column("Оборот", "currency", 140),
            Column("Статус", "text", 120),
        ),
        kpi_names=(
            "Позиций на складе",
            "Стоимость запасов",
            "Оборачиваемость",
            "Дефицит",
            "Излишки",
        ),
        chart_column=4,
        chart_title="Оборот по позициям",
        total_kinds=("empty", "empty", "sum", "sum", "sum", "empty"),
    ),
    "Маркетинг": ReportSchema(
        name="Маркетинг",
        columns=(
            Column("Канал", "text", 200),
            Column("Показы", "integer", 120),
            Column("Клики", "integer", 110),
            Column("CTR", "percent", 100),
            Column("Расход", "currency", 140),
            Column("Заявки", "integer", 100),
        ),
        kpi_names=("Расход", "Заявки", "CPL", "CTR", "ROMI"),
        chart_column=4,
        chart_title="Расход по каналам",
        total_kinds=("empty", "sum", "sum", "value", "sum", "sum"),
    ),
    "HR": ReportSchema(
        name="HR",
        columns=(
            Column("Подразделение", "text", 200),
            Column("Численность", "integer", 120),
            Column("Принято", "integer", 100),
            Column("Уволено", "integer", 100),
            Column("Текучесть", "percent", 110),
            Column("Вакансии", "integer", 100),
        ),
        kpi_names=("Численность", "Принято", "Уволено", "Текучесть", "Вакансии"),
        chart_column=1,
        chart_title="Численность по подразделениям",
        total_kinds=("empty", "sum", "sum", "sum", "value", "sum"),
    ),
}

REPORT_TYPES = tuple(REPORT_SCHEMAS)


@dataclass
class KPI:
    name: str
    value: float
    unit: str
    change_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 2),
            "unit": self.unit,
            "change_pct": round(self.change_pct, 1),
        }


@dataclass
class ReportData:
    report_type: str
    period_start: date
    period_end: date
    department: str
    author: str
    generated_at: datetime
    columns: list[str]
    rows: list[list[Any]]
    totals: list[Any]
    kpis: list[KPI]
    seed: int | None = None
    schema: ReportSchema = field(repr=False, default=None)  # type: ignore[assignment]

    @property
    def title(self) -> str:
        return f"Аналитический отчёт «{self.report_type}»"

    @property
    def period_label(self) -> str:
        return (
            f"за период с {self.period_start:%d.%m.%Y} "
            f"по {self.period_end:%d.%m.%Y}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "department": self.department,
            "author": self.author,
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "columns": self.columns,
            "rows": [
                [value.isoformat() if isinstance(value, date) else value for value in row]
                for row in self.rows
            ],
            "totals": [
                value.isoformat() if isinstance(value, date) else value
                for value in self.totals
            ],
            "kpis": [kpi.to_dict() for kpi in self.kpis],
            "seed": self.seed,
        }

    def to_ai_context(self) -> dict[str, Any]:
        """Компактный контекст для языковой модели."""

        top_rows = []
        for row in self.rows[:5]:
            top_rows.append(
                {
                    "row": {
                        title: _human_value(value, column.kind)
                        for title, value, column in zip(self.columns, row, self.schema.columns)
                    }
                }
            )
        return {
            "report_type": self.report_type,
            "period": f"{self.period_start:%d.%m.%Y} — {self.period_end:%d.%m.%Y}",
            "department": self.department,
            "kpis": [
                {
                    "name": kpi.name,
                    "value": f"{_format_number(kpi.value)} {kpi.unit}".strip(),
                    "change_pct": kpi.change_pct,
                }
                for kpi in self.kpis
            ],
            "top_rows": top_rows,
            "totals": {
                title: _human_value(value, column.kind)
                for title, value, column in zip(self.columns, self.totals, self.schema.columns)
                if column.kind in {"currency", "integer", "percent"} and value != ""
            },
        }


def _format_number(value: float) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    if text.endswith(",00"):
        text = text[:-3]
    return text


def _human_value(value: Any, kind: str) -> str:
    if value is None or value == "":
        return ""
    if kind == "date" and isinstance(value, str):
        try:
            return date.fromisoformat(value).strftime("%d.%m.%Y")
        except ValueError:
            return value
    if kind == "currency":
        return f"{_format_number(float(value))} ₽"
    if kind == "percent":
        return f"{float(value) * 100:.1f} %".replace(".", ",")
    if kind == "integer":
        return f"{int(value):,}".replace(",", " ")
    return str(value)


class ReportDataGenerator:
    """Генератор данных отчёта."""

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed

    def generate(
        self,
        report_type: str,
        period_start: date,
        period_end: date,
        department: str = "Все подразделения",
        author: str = "",
    ) -> ReportData:
        if report_type not in REPORT_SCHEMAS:
            raise ValueError(
                f"Неизвестный тип отчёта: {report_type!r}. "
                f"Доступные: {', '.join(REPORT_TYPES)}"
            )
        if period_end < period_start:
            raise ValueError("Дата окончания периода не может быть раньше даты начала")
        if (period_end - period_start).days > 366:
            raise ValueError("Период не должен превышать 366 дней")

        schema = REPORT_SCHEMAS[report_type]
        rng = random.Random(self.seed)

        builders = {
            "Продажи": self._build_sales,
            "Финансы": self._build_finance,
            "Склад": self._build_warehouse,
            "Маркетинг": self._build_marketing,
            "HR": self._build_hr,
        }
        rows, totals, kpis = builders[report_type](rng, period_start, period_end, schema)

        return ReportData(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            department=department or "Все подразделения",
            author=author,
            generated_at=datetime.now(),
            columns=[column.title for column in schema.columns],
            rows=rows,
            totals=totals,
            kpis=kpis,
            seed=self.seed,
            schema=schema,
        )

    # ------------------------------------------------------------------
    # Типы отчётов
    # ------------------------------------------------------------------
    def _build_sales(
        self,
        rng: random.Random,
        start: date,
        end: date,
        schema: ReportSchema,
    ) -> tuple[list[list[Any]], list[Any], list[KPI]]:
        days = (end - start).days + 1
        count = max(10, min(days, 30))
        if days >= count:
            step = (days - 1) / max(count - 1, 1)
            dates = [start + timedelta(days=round(index * step)) for index in range(count)]
        else:
            dates = [start + timedelta(days=index % max(days, 1)) for index in range(count)]
        dates.sort()

        rows: list[list[Any]] = []
        for index, current in enumerate(dates):
            operations = rng.randint(5, 120)
            average_check = round(rng.uniform(800, 4500), 2)
            total = round(operations * average_check, 2)
            rows.append(
                [
                    current.isoformat(),
                    SALES_CATEGORIES[index % len(SALES_CATEGORIES)],
                    operations,
                    total,
                    average_check,
                    None,
                ]
            )

        grand_total = sum(row[3] for row in rows)
        for row in rows:
            row[5] = round(row[3] / grand_total, 4) if grand_total else 0.0

        total_operations = sum(row[2] for row in rows)
        avg_check = grand_total / total_operations if total_operations else 0.0
        totals: list[Any] = ["", "", total_operations, round(grand_total, 2), round(avg_check, 2), 1.0]

        conversion = round(rng.uniform(8, 25), 1)
        growth = round(rng.uniform(-12, 25), 1)
        kpis = [
            KPI("Выручка", round(grand_total, 2), "₽", growth),
            KPI("Количество операций", float(total_operations), "шт.", round(rng.uniform(-8, 18), 1)),
            KPI("Средний чек", round(avg_check, 2), "₽", round(rng.uniform(-5, 12), 1)),
            KPI("Конверсия", conversion, "%", round(rng.uniform(-3, 6), 1)),
            KPI("Прирост к предыдущему периоду", growth, "%", 0.0),
        ]
        return rows, totals, kpis

    def _build_finance(
        self,
        rng: random.Random,
        start: date,
        end: date,
        schema: ReportSchema,
    ) -> tuple[list[list[Any]], list[Any], list[KPI]]:
        rows: list[list[Any]] = []
        plan_total = 0.0
        fact_total = 0.0

        for article in FINANCE_ARTICLES:
            plan = round(rng.uniform(200_000, 2_000_000), 2)
            fact = round(plan * rng.uniform(0.78, 1.18), 2)
            deviation = round(fact - plan, 2)
            execution = round(fact / plan, 4) if plan else 0.0
            if article == "Выручка":
                plan_total += plan
                fact_total += fact
            if execution >= 1.05:
                comment = "Перевыполнение"
            elif execution <= 0.9:
                comment = "Требует внимания"
            else:
                comment = "В пределах плана"
            rows.append([article, plan, fact, deviation, execution, comment])

        total_plan = sum(row[1] for row in rows)
        total_fact = sum(row[2] for row in rows)
        total_deviation = total_fact - total_plan
        total_execution = total_fact / total_plan if total_plan else 0.0
        totals: list[Any] = [
            "",
            round(total_plan, 2),
            round(total_fact, 2),
            round(total_deviation, 2),
            round(total_execution, 4),
            "",
        ]

        income = float(rows[0][2])
        expenses = float(total_fact - income)
        profit = income - expenses
        margin = profit / income if income else 0.0
        plan_gap = (total_fact - total_plan) / total_plan if total_plan else 0.0
        kpis = [
            KPI("Доходы", round(income, 2), "₽", round(rng.uniform(-5, 15), 1)),
            KPI("Расходы", round(expenses, 2), "₽", round(rng.uniform(-10, 12), 1)),
            KPI("Прибыль", round(profit, 2), "₽", round(rng.uniform(-15, 20), 1)),
            KPI("Маржинальность", round(margin * 100, 1), "%", round(rng.uniform(-2, 4), 1)),
            KPI("Отклонение от плана", round(plan_gap * 100, 1), "%", 0.0),
        ]
        return rows, totals, kpis

    def _build_warehouse(
        self,
        rng: random.Random,
        start: date,
        end: date,
        schema: ReportSchema,
    ) -> tuple[list[list[Any]], list[Any], list[KPI]]:
        rows: list[list[Any]] = []
        for index in range(12):
            stock = rng.randint(0, 500)
            reserve = rng.randint(0, stock)
            turnover = round(rng.uniform(10_000, 900_000), 2)
            if stock < 20:
                status = "Дефицит"
            elif stock > 400:
                status = "Излишек"
            else:
                status = "Норма"
            rows.append(
                [f"SKU-{1000 + index}", WAREHOUSE_ITEMS[index % len(WAREHOUSE_ITEMS)], stock, reserve, turnover, status]
            )

        total_stock = sum(row[2] for row in rows)
        total_reserve = sum(row[3] for row in rows)
        total_turnover = sum(row[4] for row in rows)
        totals: list[Any] = ["", "", total_stock, total_reserve, round(total_turnover, 2), ""]

        deficit = sum(1 for row in rows if row[5] == "Дефицит")
        excess = sum(1 for row in rows if row[5] == "Излишек")
        kpis = [
            KPI("Позиций на складе", float(len(rows)), "шт.", 0.0),
            KPI("Стоимость запасов", round(total_turnover, 2), "₽", round(rng.uniform(-8, 14), 1)),
            KPI("Оборачиваемость", float(rng.randint(15, 45)), "дн.", round(rng.uniform(-10, 10), 1)),
            KPI("Дефицит", float(deficit), "шт.", round(rng.uniform(-20, 20), 1)),
            KPI("Излишки", float(excess), "шт.", round(rng.uniform(-15, 15), 1)),
        ]
        return rows, totals, kpis

    def _build_marketing(
        self,
        rng: random.Random,
        start: date,
        end: date,
        schema: ReportSchema,
    ) -> tuple[list[list[Any]], list[Any], list[KPI]]:
        rows: list[list[Any]] = []
        for channel in MARKETING_CHANNELS:
            impressions = rng.randint(10_000, 500_000)
            ctr = rng.uniform(0.005, 0.06)
            clicks = max(1, int(impressions * ctr))
            ctr = round(clicks / impressions, 4)
            spend = round(rng.uniform(10_000, 300_000), 2)
            leads = max(1, int(clicks * rng.uniform(0.02, 0.10)))
            rows.append([channel, impressions, clicks, ctr, spend, leads])

        total_impressions = sum(row[1] for row in rows)
        total_clicks = sum(row[2] for row in rows)
        total_spend = sum(row[4] for row in rows)
        total_leads = sum(row[5] for row in rows)
        totals: list[Any] = [
            "",
            total_impressions,
            total_clicks,
            round(total_clicks / total_impressions, 4) if total_impressions else 0.0,
            round(total_spend, 2),
            total_leads,
        ]

        cpl = total_spend / total_leads if total_leads else 0.0
        ctr_total = total_clicks / total_impressions if total_impressions else 0.0
        kpis = [
            KPI("Расход", round(total_spend, 2), "₽", round(rng.uniform(-10, 15), 1)),
            KPI("Заявки", float(total_leads), "шт.", round(rng.uniform(-5, 25), 1)),
            KPI("CPL", round(cpl, 2), "₽", round(rng.uniform(-12, 8), 1)),
            KPI("CTR", round(ctr_total * 100, 2), "%", round(rng.uniform(-1, 3), 1)),
            KPI("ROMI", round(rng.uniform(80, 350), 1), "%", round(rng.uniform(-20, 30), 1)),
        ]
        return rows, totals, kpis

    def _build_hr(
        self,
        rng: random.Random,
        start: date,
        end: date,
        schema: ReportSchema,
    ) -> tuple[list[list[Any]], list[Any], list[KPI]]:
        rows: list[list[Any]] = []
        for department in HR_DEPARTMENTS:
            headcount = rng.randint(10, 200)
            hired = rng.randint(0, 15)
            fired = rng.randint(0, min(12, headcount))
            turnover = round(fired / headcount, 4) if headcount else 0.0
            vacancies = rng.randint(0, 10)
            rows.append([department, headcount, hired, fired, turnover, vacancies])

        total_headcount = sum(row[1] for row in rows)
        total_hired = sum(row[2] for row in rows)
        total_fired = sum(row[3] for row in rows)
        total_vacancies = sum(row[5] for row in rows)
        turnover_total = total_fired / total_headcount if total_headcount else 0.0
        totals: list[Any] = [
            "",
            total_headcount,
            total_hired,
            total_fired,
            round(turnover_total, 4),
            total_vacancies,
        ]

        kpis = [
            KPI("Численность", float(total_headcount), "чел.", round(rng.uniform(-3, 8), 1)),
            KPI("Принято", float(total_hired), "чел.", round(rng.uniform(-10, 20), 1)),
            KPI("Уволено", float(total_fired), "чел.", round(rng.uniform(-15, 10), 1)),
            KPI("Текучесть", round(turnover_total * 100, 1), "%", round(rng.uniform(-2, 4), 1)),
            KPI("Вакансии", float(total_vacancies), "шт.", round(rng.uniform(-10, 15), 1)),
        ]
        return rows, totals, kpis


def validate_period(start: date, end: date, today: date | None = None) -> list[str]:
    """Проверить параметры периода. Возвращает список ошибок."""

    today = today or date.today()
    errors: list[str] = []
    if start > end:
        errors.append("Дата начала не может быть позже даты окончания")
    if (end - start).days > 366:
        errors.append("Период не должен превышать 366 дней")
    if end > today:
        errors.append("Дата окончания не может быть позже текущей даты")
    return errors


def parse_date(value: str) -> date:
    """Разобрать дату в формате ДД.ММ.ГГГГ."""

    text = (value or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Некорректная дата: {value!r}. Ожидается формат ДД.ММ.ГГГГ")
