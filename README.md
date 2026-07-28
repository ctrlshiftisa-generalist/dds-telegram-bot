# ДДС Telegram Bot

Telegram-бот для добавления финансовых заявок в Google Sheets (лист «ДДС» + «Оплаты»).

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
│   │   ├── request.py       # Request creation flow
│   │   └── admin.py         # Admin commands
│   └── services/
│       └── sheets.py        # Google Sheets integration (header-based)
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
   - `PAYMENTS_SHEET_ID` — ID таблицы «Оплаты» (если другая таблица)
   - `OWNER_ID` — Telegram ID овнера (имеет права developer)
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — содержимое service_account.json одной строкой
   - `DATABASE_PATH` — `/data/bot.db` (установлено в Dockerfile)
   - `DDS_HEADER_ROW` — строка заголовков в ДДС (по умолчанию: 4)
   - `PAYMENTS_HEADER_ROW` — строка заголовков в Оплаты (по умолчанию: 2)

## Формат листа ДДС

Заголовки находятся на **строке 4** (оранжевые). Данные начинаются со строки 5.
Бот находит колонки автоматически по названию заголовка (регистр не важен).

| Заголовок в таблице | Данные бота        | Бот заполняет? |
|----------------------|--------------------|----------------|
| Дата               | дд.мм.гггг          | ✅              |
| Тип операции      | Съёмки / Пиар...   | ✅              |
| Сумма               | число              | ✅              |
| Пользователь        | имя из Списки!C    | ✅              |
| Получатель         | —                  | ❌ (вручную)   |
| Проект               | название проекта   | ✅              |
| За период           | напр. «июль 2026»  | ✅              |
| Комментарий        | реквизиты          | ✅              |
| Оплата              | — (чекбокс)       | ❌ (вручную)   |

## Формат листов «Оплаты»

Каждый лист называется по имени проекта (например `A.M. Maison`, `Mango`, `AIN`).
**Строка 1**: техническая (Сегодняшняя дата, Без пробелов...). **Заголовки на строке 2**. Данные со строки 3.

| Заголовок в таблице | Данные бота      | Бот заполняет? |
|----------------------|------------------|----------------|
| Дата заявки       | дд.мм.гггг        | ✅              |
| Сумма               | число            | ✅              |
| Комментарий        | реквизиты (Пиар/Подписки/Другое) | ✅ |
| Карта или Р/С      | номер карты (Съёмки) | ✅ только для Съёмки |
| Оплата              | — (чекбокс)     | ❌ (вручную)   |

## Флоу заявки

```
Тип операции
├── Съёмки → выбор проекта → сумма → реквизиты (16 цифр карты)
│     └── Пишет: ДДС + Оплаты[проект]
├── Пиар → выбор проекта → сумма → реквизиты (карта + назначение)
│     └── Пишет: ДДС + Оплаты[проект]
├── Подписки → сумма → реквизиты (авто-проект: A.M. Maison)
│     └── Пишет: ДДС + Оплаты[A.M. Maison]
└── Другое → сумма → реквизиты (авто-проект: A.M. Maison)
      └── Пишет: ДДС + Оплаты[A.M. Maison]
```

## Права доступа

| Команда           | Кто может |
|-------------------|-----------|
| `/start`          | Все       |
| `📝 Создать заявку` | Все зарегистрированные |
| `/add_entity`     | Developer + Owner |
| `/add_project`    | Developer + Owner |
| `/add_admin`      | Developer + Owner |
| `/remove_admin`   | Developer + Owner |
| `/list_admins`    | Developer + Owner |
| `/list_entities`  | Developer + Owner |

## Умная запись (header-based)

Бот **не использует жёстких координат**. Алгоритм записи:

1. Читает строку заголовков из таблицы
2. Находит нужную колонку по имени (без учёта регистра)
3. Находит первую пустую строку в этой колонке
4. Записывает данные через `values().update()`

Это значит: можно переставлять столбцы в таблице — бот найдёт их автоматически.
