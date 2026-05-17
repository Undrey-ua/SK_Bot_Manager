# SK Bot Manager — Telegram CRM для торгової команди

Telegram-бот для регіональних менеджерів: фіксація візитів до торгових точок (клієнтів) з типом візиту, задачами, коментарем і фото.

## Стек

- Python 3.12
- [aiogram 3](https://docs.aiogram.dev/) — Telegram Bot API
- [SQLAlchemy 2](https://docs.sqlalchemy.org/) + asyncpg — PostgreSQL (Supabase)
- [Supabase](https://supabase.com/) — БД + Storage для фото
- Pydantic Settings — конфігурація
- Railway — деплой

## Структура проєкту

```
├── bot/
│   ├── handlers/       # Роутери: /start, клієнти, FSM візиту
│   ├── keyboards/      # Inline-клавіатури
│   ├── states/         # FSM стани
│   ├── services/       # Бізнес-логіка
│   ├── middlewares/    # DB session, авторизація
│   └── container.py    # Dependency injection
├── database/
│   ├── models.py       # SQLAlchemy моделі
│   ├── session.py      # Async engine / session
│   ├── repositories/   # Доступ до даних
│   └── schema.sql      # SQL для Supabase
├── config/
│   └── settings.py     # Pydantic Settings
├── utils/
│   └── logging.py
└── main.py             # Точка входу
```

## Швидкий старт (локально)

### 1. Клонування та віртуальне середовище

```bash
cd SK_Bot_Manager
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Налаштування `.env`

```bash
cp .env.example .env
```

Заповніть змінні (див. розділ Supabase нижче).

### 3. База даних

У Supabase SQL Editor виконайте `database/schema.sql`, потім додайте менеджера:

```sql
INSERT INTO users (telegram_id, name, role)
VALUES (YOUR_TELEGRAM_ID, 'Ваше Імʼя', 'manager');

INSERT INTO clients (manager_id, name, type, district, address)
VALUES (1, 'Тестовий магазин', 'retail', 'Київ', 'вул. Приклад, 1');
```

`YOUR_TELEGRAM_ID` — дізнайтесь у [@userinfobot](https://t.me/userinfobot).

### 4. Storage bucket

У Supabase: **Storage → New bucket** → імʼя `visit-photos` → Public (або налаштуйте RLS policy для service role).

### 5. Запуск бота

```bash
python main.py
```

У Telegram: `/start` → головне меню → **Новий візит**.

## Підключення Supabase

| Змінна | Де взяти |
|--------|----------|
| `DATABASE_URL` | Project Settings → Database → Connection string → URI. Замініть `postgresql://` на `postgresql+asyncpg://`. Для production краще **Transaction pooler** (порт 6543). |
| `SUPABASE_URL` | Project Settings → API → Project URL |
| `SUPABASE_KEY` | Project Settings → API → `service_role` key (для Storage upload) |
| `SUPABASE_STORAGE_BUCKET` | Імʼя bucket, напр. `visit-photos` |

> **Важливо:** не комітьте `.env` у git. Service role key — лише на сервері.

## Деплой на Railway

1. Створіть проєкт на [railway.app](https://railway.app).
2. **New → GitHub Repo** (або Deploy from local).
3. Додайте змінні середовища з `.env.example`.
4. Railway зчитає `railway.json` і збере образ з `Dockerfile`.
5. Після деплою бот працює у режимі long polling (`start_polling`).

Для webhook на Railway потрібен публічний URL і окрема налаштування — для MVP достатньо polling.

## FSM flow «Новий візит»

1. Вибір клієнта (inline)
2. Тип: ПВХ / Стенд
3. Задачі (checkbox toggle)
4. Коментар (текст або `-`)
5. Завантаження фото → **Завершити**
6. Збереження в `visits`, `visit_tasks`, `visit_photos`

## Авторизація

Доступ лише для `telegram_id`, що є в таблиці `users`. Незареєстровані користувачі бачать повідомлення зі своїм ID для передачі адміністратору.

## Ліцензія

Private / internal use.
