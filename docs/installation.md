# Руководство по установке

Документ описывает установку Excel Factory с нуля на рабочую станцию Windows.

## 1. Установка Python

1. Скачайте Python 3.10 или новее с [python.org](https://www.python.org/downloads/).
2. При установке отметьте пункт **Add python.exe to PATH**.
3. Проверьте установку:

```powershell
python --version
python -m pip --version
```

## 2. Получение проекта

```powershell
git clone https://github.com/markmus11012020-max/Auto-Report-GoogleSheets.git
cd Auto-Report-GoogleSheets
```

Либо распакуйте архив проекта в любую папку, например `D:\Auto-Report-GoogleSheets`.

## 3. Виртуальное окружение (рекомендуется)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Если PowerShell блокирует активацию:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 4. Установка зависимостей

```powershell
python -m pip install -r requirements.txt
```

Проверка:

```powershell
python -c "import googleapiclient, google.oauth2, openai, dotenv; print('OK')"
```

## 5. Настройка Google Cloud

### 5.1. Проект

1. Откройте [Google Cloud Console](https://console.cloud.google.com/).
2. Создайте проект, например `Excel Factory`.

### 5.2. Google Sheets API

1. Перейдите в **APIs & Services → Library**.
2. Найдите **Google Sheets API** и нажмите **Enable**.

### 5.3. Сервисный аккаунт

1. Перейдите в **IAM & Admin → Service Accounts**.
2. Нажмите **Create Service Account**.
3. Укажите имя, например `excel-factory`.
4. Роль на уровне проекта не требуется — доступ выдаётся на конкретную таблицу.
5. Откройте созданный аккаунт → **Keys → Add key → Create new key → JSON**.
6. Скачайте файл и переименуйте его в `service_account.json`.
7. Положите файл в корень проекта.

В JSON-ключе есть поле `client_email` — это адрес сервисного аккаунта,
например `excel-factory@my-project.iam.gserviceaccount.com`.

### 5.4. Google Таблица

1. Создайте новую Google Таблицу.
2. Нажмите **Настройки доступа** (Share).
3. Добавьте `client_email` сервисного аккаунта с ролью **Editor**.
4. Скопируйте идентификатор из URL:

```
https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
```

## 6. Файл конфигурации

Скопируйте шаблон:

```powershell
Copy-Item .env.example .env
```

Заполните `.env`:

```env
GOOGLE_CREDENTIALS_FILE=service_account.json
SPREADSHEET_ID=1AbC...ваш_id...XyZ

AITUNNEL_API_KEY=sk-aitunnel-...
AITUNNEL_BASE_URL=https://api.aitunnel.ru/v1
AITUNNEL_MODEL=deepseek-v4.1-flash-1017
AI_TIMEOUT=30
AI_RETRIES=2

LOG_LEVEL=INFO
REPORT_SEED=
```

`REPORT_SEED` можно оставить пустым: тогда каждый отчёт будет уникальным.
Для воспроизводимых демонстраций укажите целое число, например `42`.

## 7. Проверка подключения

```powershell
python google_sheets.py
```

Ожидаемый результат:

```
Таблица: Моя таблица
Ссылка:  https://docs.google.com/spreadsheets/d/.../edit
Листов:  1

=== Лист: Лист1 ===
Строк: 0, столбцов: 0
(лист пуст)
```

Если появилась ошибка — см. раздел 9.

## 8. Запуск приложения

```powershell
python report_generator.py
```

1. Укажите период (формат `ДД.ММ.ГГГГ`).
2. Выберите тип отчёта.
3. При необходимости измените подразделение и автора.
4. Нажмите **Сгенерировать отчёт**.
5. Дождитесь ссылки в блоке «Результат».

## 9. Типовые ошибки

| Ошибка | Причина | Решение |
|---|---|---|
| `Не найден файл ключа` | Нет `service_account.json` | Положить файл в корень или изменить `GOOGLE_CREDENTIALS_FILE` |
| `Не удалось прочитать JSON-ключ` | Повреждён файл | Скачать ключ заново |
| `Доступ запрещён (403)` | Таблица не открыта аккаунту | Выдать доступ `client_email` с ролью Editor |
| `Google Sheets API has not been used` | API не включён | Включить Google Sheets API в проекте |
| `Таблица не найдена (404)` | Неверный `SPREADSHEET_ID` | Скопировать ID из URL |
| `Не установлен пакет openai` | Не выполнена установка | `pip install -r requirements.txt` |
| ИИ не отвечает | Нет сети или ключа | Отчёт создастся с резервным текстом; проверить `.env` |

Журнал: `logs/app.log`.

## 10. Обновление

```powershell
git pull
python -m pip install -r requirements.txt --upgrade
```
