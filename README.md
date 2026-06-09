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
├── web/
│   ├── app.py          # FastAPI + шаблони
│   ├── templates/      # HTML панель
│   └── services/       # Запити для дашборду
├── utils/
│   └── logging.py
├── main.py             # Telegram-бот
└── web_main.py         # Веб-панель керівника
```

## Швидкий старт (локально)

### 1. Клонування та віртуальне середовище

```bash
cd SK_Bot_Manager
python3.12 -m venv .venv    # мінімум Python 3.10; 3.12 рекомендовано
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
VALUES (535827585, 'Ваше Імʼя', 'manager');

INSERT INTO clients (manager_id, name, type, district, address)
VALUES (1, 'Тестовий магазин', 'retail', 'Київ', 'вул. Приклад, 1');
```

`Y535827585` — дізнайтесь у [@userinfobot](https://t.me/userinfobot).

### 4. Storage bucket

У Supabase: **Storage → New bucket** → імʼя `visit-photos` → Public (або налаштуйте RLS policy для service role).

### 5. Запуск бота

```bash
python main.py
# або явно з venv (не системний python3):
# .venv/bin/python main.py
```

У Telegram: `/start` → головне меню → **Новий візит**.

## Підключення Supabase

| Змінна | Де взяти |
|--------|----------|
| `DATABASE_URL` | Dashboard → **Connect** → URI → **Transaction pooler** (6543). Скопіюйте host **з Dashboard**, не з прикладу. Префікс: `postgresql+asyncpg://` |
| `SUPABASE_URL` | Project Settings → API → Project URL |
| `SUPABASE_KEY` | Settings → **API Keys** → **Secret keys** → `sb_secret_...` (або legacy service_role `eyJ...`) |
| `SUPABASE_STORAGE_BUCKET` | Storage → bucket `visit-photos` → **Public bucket** |

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

## Веб-панель для керівника

Окремий сервіс показує всю інформацію з бота: візити (задачі, коментарі, фото), клієнтів, статистику по менеджерах.

### Локально

```bash
# У .env додайте:
# DASHBOARD_PASSWORD=надійний_пароль
python web_main.py
```

Відкрийте http://localhost:8000 — увійдіть паролем з `DASHBOARD_PASSWORD`.

### Railway (другий сервіс)

1. У тому ж репозиторії створіть **другий сервіс** (бот залишається на `python main.py`).
2. Start command: `python web_main.py`
3. Додайте ті самі змінні, що й у бота, плюс `DASHBOARD_PASSWORD`.
4. У Settings → Networking увімкніть публічний домен і вкажіть порт `8000` (або `WEB_PORT`).

Альтернатива: скопіюйте `railway.web.json` у `railway.json` для окремого деплою панелі.

## Авторизація

**Telegram-бот:** доступ лише для `telegram_id`, що є в таблиці `users`. Незареєстровані користувачі бачать повідомлення зі своїм ID для передачі адміністратору.

**Веб-панель:** пароль із `DASHBOARD_PASSWORD` (окремо від Telegram).

## Клієнти, області, стенди

- **👤 Клієнти** — додавання/редагування клієнта (назва, область, адреса, коментар, стенди).
- **🗺 Мої області** — кожен менеджер веде свій список областей.
- **🏷 Каталог стендів** — лише `role = admin` (додати/вимкнути стенди).

Адміністратор:

```sql
UPDATE users SET role = 'admin' WHERE telegram_id = YOUR_TELEGRAM_ID;
```

Міграції для існуючої БД: `database/migrations/` (зокрема `009_task_kind.sql`, `010_stand_transfers.sql`, `011_user_roles_supervisor.sql`).

**Веб-панель:** `python web_main.py` → http://localhost:8000  
- **Адмін (1):** `DASHBOARD_ADMIN_PASSWORD`, Telegram порожній; у `.env` вкажіть `DASHBOARD_ADMIN_TELEGRAM_ID=535827585` для **Андрія Вовнянка** (адмін + своє поле як регіональний менеджер).  
- **Керівник (3):** `DASHBOARD_PASSWORD` + Telegram ID, роль `leader` — повний огляд, задачі від їхнього імені.  
- **Регіональний менеджер:** роль `manager` — **Роман Ковальов**, **Павло Ковалишин**; **Андрій Вовнянко** — `role=admin`, але в полі як регіональний (див. `config/team.py`).  
- **Менеджер збуту:** роль `sales_manager`, `supervisor_id` → id регіонального менеджера; у боті лише «Резерви» та «Додати продаж», у вебі — аналітика та резерви по своєму регіональному.

### Ролі в БД (`users.role`)

| Роль | Значення | Опис |
|------|----------|------|
| Адмін | `admin` | Каталог стендів, продовження резервів, керування користувачами (А. Вовнянко — також поле) |
| Керівник | `leader` | Панель як у адміна (без каталогу стендів), створення задач від свого імені |
| Регіональний менеджер | `manager` | Свої клієнти, візити, стенди |
| Менеджер збуту | `sales_manager` | `supervisor_id` = регіональний менеджер |

Міграція: `database/migrations/011_user_roles_supervisor.sql`

Приклад призначення ролей:

```sql
-- адмін (Андрій Вовнянко — також регіональний менеджер у полі)
UPDATE users SET role = 'admin', supervisor_id = NULL WHERE telegram_id = 535827585;
-- міграція: database/migrations/012_andrii_admin_regional.sql

-- три керівники (колишні admin → leader)
UPDATE users SET role = 'leader' WHERE telegram_id IN (222222222, 333333333, 444444444);

-- регіональні (Роман, Павло)
UPDATE users SET role = 'manager', supervisor_id = NULL
WHERE telegram_id IN (5009921383, 7770797356);

-- менеджер збуту (пізніше)
INSERT INTO users (telegram_id, name, role, supervisor_id)
VALUES (555555555, 'Іван Збут', 'sales_manager', (SELECT id FROM users WHERE telegram_id = 666666666 LIMIT 1));
```

## Troubleshooting: `Tenant or user not found`

Ця помилка майже завжди означає **неправильний host pooler** у `DATABASE_URL` (скопійовано приклад `aws-0-eu-central-1` замість host вашого проєкту).

1. Supabase Dashboard → ваш проєкт → **Connect** (кнопка зверху).
2. **ORMs** → **URI** → **Transaction pooler** (порт **6543**).
3. Скопіюйте **весь** рядок і в `.env`:
   - `postgresql://` → `postgresql+asyncpg://`
   - `[YOUR-PASSWORD]` → реальний пароль (без дужок)
4. Перевірте **user**: `postgres.yjvfebhgbzpkdchvwcqp` (ref з URL проєкту).
5. **Host** має збігатися з Dashboard (напр. `aws-1-us-east-2.pooler.supabase.com`, не обовʼязково `aws-0-eu-central-1`).

Якщо пароль не памʼятаєте: **Project Settings → Database → Reset database password**.

## Ліцензія

Private / internal use.
