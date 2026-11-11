"""Excel Factory — графическое приложение для генерации отчётов.

Запуск::

    python report_generator.py
"""

from __future__ import annotations

import getpass
import json
import queue
import threading
import traceback
import webbrowser
from datetime import date, datetime
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

from ai_client import AITunnelClient
from config import Settings, get_logger, get_settings, setup_logging
from report_builder import ReportBuilder
from report_data import (
    REPORT_TYPES,
    ReportData,
    ReportDataGenerator,
    parse_date,
    validate_period,
)

LOGGER = get_logger("gui")

DEPARTMENTS = [
    "Все подразделения",
    "Отдел продаж",
    "Финансовый отдел",
    "Склад",
    "Маркетинг",
    "ИТ-отдел",
    "Отдел кадров",
    "Логистика",
]

BG = "#F4F6FA"
ACCENT = "#1F3864"
ACCENT_LIGHT = "#2E75B6"
MUTED = "#595959"
ERROR = "#C00000"
WARNING = "#B26B00"
SUCCESS = "#375623"


class AppError(Exception):
    """Понятная пользователю ошибка."""


def _quote_sheet(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


class ReportApp(tk.Tk):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.queue: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self._busy = False
        self._inputs: list[tk.Widget] = []
        self.current_url = ""

        self.title("Excel Factory — генератор отчётов")
        self.geometry("900x680")
        self.minsize(780, 600)
        self.configure(bg=BG)

        self._configure_style()
        self._build_ui()
        self._log_startup()
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------------
    # Интерфейс
    # ------------------------------------------------------------------
    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TLabel", background=BG, foreground="#262626", font=("Segoe UI", 9))
        style.configure("TLabelframe", background=BG, font=("Segoe UI", 9, "bold"))
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT)
        style.configure("TCheckbutton", background=BG, font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(18, 8))
        style.configure("TEntry", padding=4)
        style.configure("TCombobox", padding=4)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=ACCENT, height=74)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(
            header,
            text="Excel Factory",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 20, "bold"),
            anchor="w",
        ).pack(side="left", padx=24, pady=(12, 0))
        tk.Label(
            header,
            text="Автоматическое формирование отчётов в Google Таблицах",
            bg=ACCENT,
            fg="#D9E2F3",
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(side="left", padx=10, pady=(18, 0))

        form = ttk.LabelFrame(self, text=" Параметры отчёта ", padding=14)
        form.grid(row=1, column=0, sticky="ew", padx=18, pady=(14, 8))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(4, weight=1)

        ttk.Label(form, text="Период с:").grid(row=0, column=0, sticky="w", pady=5)
        self.start_entry = ttk.Entry(form, width=16)
        self.start_entry.grid(row=0, column=1, sticky="w", padx=(6, 0), pady=5)
        ttk.Label(form, text="по:").grid(row=0, column=2, sticky="w", padx=(14, 0), pady=5)
        self.end_entry = ttk.Entry(form, width=16)
        self.end_entry.grid(row=0, column=3, sticky="w", padx=(6, 0), pady=5)
        ttk.Label(form, text="Формат: ДД.ММ.ГГГГ", foreground=MUTED).grid(
            row=0, column=4, sticky="w", padx=(12, 0), pady=5
        )

        today = date.today()
        self.start_entry.insert(0, today.replace(day=1).strftime("%d.%m.%Y"))
        self.end_entry.insert(0, today.strftime("%d.%m.%Y"))

        ttk.Label(form, text="Тип отчёта:").grid(row=1, column=0, sticky="w", pady=5)
        self.type_combo = ttk.Combobox(
            form, values=list(REPORT_TYPES), state="readonly", width=26
        )
        self.type_combo.current(0)
        self.type_combo.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=5)

        ttk.Label(form, text="Подразделение:").grid(
            row=2, column=0, sticky="w", pady=5
        )
        self.department_combo = ttk.Combobox(form, values=DEPARTMENTS, width=26)
        self.department_combo.current(0)
        self.department_combo.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=5)

        ttk.Label(form, text="Автор:").grid(row=2, column=2, sticky="w", padx=(14, 0), pady=5)
        self.author_entry = ttk.Entry(form, width=18)
        self.author_entry.grid(row=2, column=3, sticky="w", padx=(6, 0), pady=5)
        try:
            self.author_entry.insert(0, getpass.getuser())
        except Exception:  # noqa: BLE001
            pass

        self.use_ai_var = tk.BooleanVar(value=True)
        self.use_chart_var = tk.BooleanVar(value=True)
        checks = tk.Frame(form, bg=BG)
        checks.grid(row=3, column=0, columnspan=5, sticky="w", pady=(8, 2))
        ttk.Checkbutton(
            checks, text="Аналитический вывод ИИ", variable=self.use_ai_var
        ).pack(side="left")
        ttk.Checkbutton(
            checks, text="Диаграмма", variable=self.use_chart_var
        ).pack(side="left", padx=(18, 0))

        actions = tk.Frame(form, bg=BG)
        actions.grid(row=4, column=0, columnspan=5, sticky="ew", pady=(10, 0))
        self.generate_btn = ttk.Button(
            actions,
            text="Сгенерировать отчёт",
            style="Accent.TButton",
            command=self.on_generate,
        )
        self.generate_btn.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=220)
        self.progress.pack(side="left", padx=(16, 0))

        self._inputs = [
            self.start_entry,
            self.end_entry,
            self.type_combo,
            self.department_combo,
            self.author_entry,
            self.generate_btn,
            *(child for child in checks.winfo_children() if isinstance(child, ttk.Checkbutton)),
        ]

        log_frame = ttk.LabelFrame(self, text=" Журнал ", padding=8)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=8)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            bg="white",
            fg="#262626",
            relief="flat",
            font=("Consolas", 9),
            padx=8,
            pady=6,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.tag_config("error", foreground=ERROR)
        self.log_text.tag_config("warning", foreground=WARNING)
        self.log_text.tag_config("success", foreground=SUCCESS)
        self.log_text.tag_config("muted", foreground=MUTED)

        link_frame = ttk.LabelFrame(self, text=" Результат ", padding=10)
        link_frame.grid(row=3, column=0, sticky="ew", padx=18, pady=(6, 16))
        link_frame.columnconfigure(1, weight=1)

        ttk.Label(link_frame, text="Ссылка на отчёт:").grid(row=0, column=0, sticky="w")
        self.link_label = tk.Label(
            link_frame,
            text="—",
            bg=BG,
            fg=ACCENT_LIGHT,
            cursor="hand2",
            anchor="w",
            justify="left",
            font=("Segoe UI", 9, "underline"),
        )
        self.link_label.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.link_label.bind("<Button-1>", self._open_link)
        self.copy_btn = ttk.Button(
            link_frame, text="Копировать", command=self._copy_link, state="disabled"
        )
        self.copy_btn.grid(row=0, column=2, sticky="e")

        self.bind("<Control-Return>", lambda _event: self.on_generate())

    # ------------------------------------------------------------------
    # Журнал
    # ------------------------------------------------------------------
    def _append_log(self, message: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        prefix = f"{datetime.now():%H:%M:%S}  "
        self.log_text.insert("end", prefix + message + "\n", tag or "")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_startup(self) -> None:
        self._append_log("Excel Factory запущен.", "muted")
        if self.settings.google_problems():
            self._append_log(
                "Google Таблица не настроена: " + "; ".join(self.settings.google_problems()),
                "warning",
            )
            self._append_log(
                "Заполните .env и положите JSON-ключ сервисного аккаунта в корень проекта.",
                "muted",
            )
        else:
            self._append_log("Подключение к Google Таблицам настроено.", "success")
        if self.settings.ai_enabled:
            self._append_log(
                f"ИИ: {self.settings.ai_model} ({self.settings.ai_base_url}).",
                "muted",
            )
        else:
            self._append_log(
                "ИИ не настроен — будет использован резервный текст.", "warning"
            )

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------
    def on_generate(self) -> None:
        if self._busy:
            return
        try:
            params = self._collect_params()
        except AppError as exc:
            messagebox.showerror("Проверьте параметры", str(exc), parent=self)
            self._append_log(str(exc), "error")
            return

        self._set_busy(True)
        self.current_url = ""
        self.link_label.configure(text="—")
        self.copy_btn.configure(state="disabled")
        self._append_log("—" * 52, "muted")
        self._append_log(
            f"Генерация отчёта «{params['report_type']}» "
            f"за {params['start']:%d.%m.%Y} — {params['end']:%d.%m.%Y}",
            "muted",
        )

        thread = threading.Thread(target=self._run_generation, args=(params,), daemon=True)
        thread.start()

    def _collect_params(self) -> dict[str, Any]:
        try:
            start = parse_date(self.start_entry.get())
            end = parse_date(self.end_entry.get())
        except ValueError as exc:
            raise AppError(str(exc)) from exc

        errors = validate_period(start, end)
        if errors:
            raise AppError("\n".join(errors))

        report_type = self.type_combo.get().strip()
        if report_type not in REPORT_TYPES:
            raise AppError("Выберите тип отчёта из списка")

        department = self.department_combo.get().strip() or "Все подразделения"
        author = self.author_entry.get().strip()
        if len(department) > 100:
            raise AppError("Название подразделения не должно превышать 100 символов")
        if len(author) > 100:
            raise AppError("Имя автора не должно превышать 100 символов")

        return {
            "start": start,
            "end": end,
            "report_type": report_type,
            "department": department,
            "author": author,
            "use_ai": self.use_ai_var.get(),
            "use_chart": self.use_chart_var.get(),
        }

    # ------------------------------------------------------------------
    # Фоновая генерация
    # ------------------------------------------------------------------
    def _run_generation(self, params: dict[str, Any]) -> None:
        try:
            google_problems = self.settings.google_problems()
            if google_problems:
                raise AppError(
                    "Не настроено подключение к Google Таблицам:\n"
                    + "\n".join(f"• {problem}" for problem in google_problems)
                )

            self._post("log", "Формирование данных отчёта…")
            generator = ReportDataGenerator(seed=self.settings.report_seed)
            report = generator.generate(
                report_type=params["report_type"],
                period_start=params["start"],
                period_end=params["end"],
                department=params["department"],
                author=params["author"],
            )
            self._post("log", f"Данные сформированы: {len(report.rows)} строк.")

            ai_text = self._generate_ai_text(report, params["use_ai"])
            layout = ReportBuilder().build(report, ai_text)
            self._post("log", f"Макет отчёта готов: {layout.footer_row} строк, 6 столбцов.")

            try:
                from google_sheets import GoogleSheetsClient, SheetsError, quote_sheet
            except ImportError as exc:
                raise AppError(
                    "Не установлены зависимости Google API. "
                    "Выполните: pip install -r requirements.txt"
                ) from exc

            self._post("log", "Подключение к Google Sheets…")
            client = GoogleSheetsClient.from_settings(self.settings)
            try:
                client.connect()
                self._post("log", "Подключение установлено.", "success")

                title = self._unique_title(client.list_sheets(), report)
                self._post("log", f"Создание листа «{title}»…")
                sheet_id = client.create_sheet(title)

                self._post("log", "Запись данных…")
                client.update_range(f"{quote_sheet(title)}!A1", layout.values)

                self._post("log", "Применение форматирования…")
                client.batch_format(sheet_id, layout.format_requests(sheet_id))

                if params["use_chart"]:
                    self._post("log", "Построение диаграммы…")
                    client.add_chart(sheet_id=sheet_id, **layout.chart_spec())

                self._post("log", "Проверка результата…")
                check = client.read_range(f"{quote_sheet(title)}!A1:F{layout.footer_row}")
                if not check:
                    raise AppError(
                        "Лист создан, но данные не прочитаны. Проверьте таблицу вручную."
                    )
                url = client.sheet_url(title)
            except SheetsError as exc:
                raise AppError(str(exc)) from exc

            self._save_cache(report, ai_text, title, url)
            self._post("done", url)
        except AppError as exc:
            LOGGER.error("Ошибка генерации: %s", exc)
            self._post("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Непредвиденная ошибка:\n%s", traceback.format_exc())
            self._post(
                "error",
                f"Непредвиденная ошибка: {exc}\nПодробности записаны в logs/app.log",
            )

    def _generate_ai_text(self, report: ReportData, use_ai: bool) -> str:
        context = report.to_ai_context()
        if not use_ai:
            self._post("log", "ИИ отключён пользователем — используется резервный текст.", "warning")
            return AITunnelClient("", "", "").fallback_summary(context)

        if not self.settings.ai_enabled:
            self._post("log", "ИИ не настроен — используется резервный текст.", "warning")
            return AITunnelClient("", "", "").fallback_summary(context)

        self._post("log", f"Запрос к ИИ ({self.settings.ai_model})…")
        result = AITunnelClient.from_settings(self.settings).generate_summary(context)
        if result.used_fallback:
            self._post(
                "log",
                f"ИИ недоступен ({result.error or 'причина неизвестна'}) — "
                "использован резервный текст.",
                "warning",
            )
        else:
            self._post("log", "Аналитический вывод получен.", "success")
        return result.text

    @staticmethod
    def _unique_title(existing: list[str], report: ReportData) -> str:
        base = (
            f"{report.report_type}_"
            f"{report.period_start:%d.%m.%Y}_{report.period_end:%d.%m.%Y}"
        )
        if len(base) > 95:
            base = base[:95]
        title = base
        suffix = 2
        known = set(existing)
        while title in known:
            title = f"{base}_{suffix}"
            suffix += 1
        return title

    def _save_cache(self, report: ReportData, ai_text: str, title: str, url: str) -> None:
        try:
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "sheet_title": title,
                "url": url,
                "ai_text": ai_text,
                "report": report.to_dict(),
            }
            cache_file = self.settings.cache_dir / "last_report.json"
            temp_file = cache_file.with_suffix(".tmp")
            temp_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_file.replace(cache_file)
            self._post("log", "Модель отчёта сохранена в cache/last_report.json.", "muted")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Не удалось сохранить кэш отчёта: %s", exc)
            self._post("log", f"Не удалось сохранить кэш: {exc}", "warning")

    # ------------------------------------------------------------------
    # Обмен с потоком
    # ------------------------------------------------------------------
    def _post(self, kind: str, message: str, tag: str = "") -> None:
        self.queue.put((kind, message, tag))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, message, tag = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(message, tag or None)
                elif kind == "done":
                    self._on_done(message)
                elif kind == "error":
                    self._on_error(message)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _on_done(self, url: str) -> None:
        self.current_url = url
        self.link_label.configure(text=url)
        self.copy_btn.configure(state="normal")
        self._append_log("Отчёт успешно создан.", "success")
        self._append_log(url, "success")
        self._set_busy(False)
        messagebox.showinfo(
            "Готово",
            "Отчёт создан и записан в Google Таблицу.\nСсылка доступна в блоке «Результат».",
            parent=self,
        )

    def _on_error(self, message: str) -> None:
        self._append_log(message, "error")
        self._set_busy(False)
        messagebox.showerror("Ошибка", message, parent=self)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in self._inputs:
            try:
                widget.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if not busy:
            self.type_combo.configure(state="readonly")
            self.generate_btn.configure(state="normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    # ------------------------------------------------------------------
    def _open_link(self, _event: object = None) -> None:
        if self.current_url:
            webbrowser.open(self.current_url)

    def _copy_link(self) -> None:
        if not self.current_url:
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_url)
        self._append_log("Ссылка скопирована в буфер обмена.", "muted")


def main() -> None:
    settings = get_settings()
    setup_logging(settings)
    LOGGER.info("Запуск приложения")
    app = ReportApp(settings)
    app.mainloop()


if __name__ == "__main__":
    main()
