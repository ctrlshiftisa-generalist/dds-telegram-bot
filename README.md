# ДДС Telegram Bot

Telegram-бот для добавления финансовых заявок в Google Sheets (лист «ДДС»).

## Стек

- Python 3.11+
- aiogram 3.x
- Google Sheets API
- SQLite (aiosqlite)
- pydantic-settings

## Структура проекта

```
dds/
├── bot/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── config.py            # Settings (pydantic-settings)
│   ├── database.py          # SQLite operations
│   ├── keyboards.py         # All keyboards
│   ├── states.py            # FSM states
│   ├── utils.py             # Number formatting, dates
│   ├── handlers/
│   │   ├── common.py        # /start, profile, help
│   │   └── request.py       # Request creation flow
│   └── services/
│       └── sheets.py        # Google Sheets integration
├── .env                     # Credentials (not in git)
├── .env.example             # Template
├── service_account.json     # Google SA credentials (not in git)
├── requirements.txt
├── Dockerfile
├── railway.toml
└── README.md
```

## Локальный запуск

```bash
# 1. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Настроить .env (скопировать из .env.example и заполнить)
cp .env.example .env

# 4. Положить service_account.json в корень проекта

# 5. Запустить бота
python -m bot
```

## Деплой на Railway

1. Создать проект на Railway и подключить GitHub-репозиторий.
2. Добавить Volume с mount path `/data` для SQLite.
3. Установить переменные окружения:
   - `BOT_TOKEN`
   - `GOOGLE_SHEET_ID`
   - `SHEET_NAME` (по умолчанию: ДДС)
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — содержимое service_account.json одной строкой
   - `DATABASE_PATH` — `/data/bot.db` (установлено в Dockerfile)

## Формат листа ДДС

| Колонка | Содержимое         | Бот заполняет? |
|---------|--------------------|----------------|
| A       | Дата (dd.mm.yyyy)  | ✅              |
| B       | Тип операции       | ✅              |
| C       | Сумма              | ✅              |
| D       | (резерв)           | ❌              |
| E       | Получатель         | ❌              |
| F       | Проект             | ✅              |
| G       | За период          | ✅              |
| H       | Комментарий        | ✅              |

Заголовки на строке 4, данные с строки 5. Бот использует `append` в диапазон `ДДС!A5:H`.
