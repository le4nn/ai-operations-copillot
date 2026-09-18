# PHASE 3 — Database

## Goal / What you will learn

Создать проверяемый источник бизнес-фактов для будущего AI: PostgreSQL,
SQLAlchemy 2, история схемы Alembic и воспроизводимые synthetic данные.
В этой фазе изучаем ORM-связи, ограничения БД, транзакции, connection pool,
миграции и разницу между технической доступностью API и готовностью работать с данными.

## Architecture / Files

FastAPI → `get_session()` → SQLAlchemy Session → Engine / pool → PostgreSQL.
Alembic отдельно обновляет схему; seed отдельно наполняет её.

| Файлы | Ответственность |
| --- | --- |
| `backend/app/db/base.py` | Общая metadata, ID, дата создания, имена ограничений |
| `backend/app/db/session.py` | Engine, пул подключений, сессия на запрос |
| `backend/app/models/business.py` | Заказы, клиенты, поставщики, курьеры, SLA и задачи |
| `backend/app/models/ai.py` | Хранение документов, чатов и будущих traces |
| `backend/alembic/` и `alembic.ini` | Версии и применение схемы |
| `backend/app/db/seed.py` | Атомарное создание демонстрационного набора |
| `backend/tests/test_database.py` | Связи, ограничения, миграции, seed и rollback |
| `backend/tests/test_readiness.py` | Readiness с настоящими SQL-запросами |
| `backend/tests/test_migration_sql.py` | Генерация PostgreSQL DDL без сервера |

Настройки, lifespan FastAPI, health, зависимости, Docker и версия frontend также обновлены.

## Модель данных

Один customer имеет много orders, каждый order принадлежит одному supplier.
У order несколько order_items и не более одной delivery. В delivery хранится courier,
а в delivery_events — история: назначение, получение, задержка, завершение.
Supplier связан с одной записью supplier_sla. Unique constraint на foreign key
обеспечивает связь «не более одного» на уровне БД; `relationship` даёт навигацию в Python.

Дополнительные связи: document → chunks; user → chat_sessions → chat_messages;
ai_trace → message/user; task → order/supplier/assigned user/approving user.
Созданы все 15 таблиц из задания. У документов пока нет embeddings;
AI-таблицы пусты, вызовы LLM и фиктивные traces не создаются.

Для первой модели предполагаем один supplier и одну доставку на order.
Повторные попытки доставки и разбиение заказа потребуют отдельного изменения модели.
Автоматическое каскадное удаление бизнес-истории не включено.

## Как работает код и почему так

`Engine` управляет пулом: соединения переиспользуются, максимум 10 на процесс.
`pool_pre_ping` проверяет соединение перед выдачей. Настроены ограничения ожидания
пула, подключения и выполнения SQL. Сессия создаётся для запроса и закрывается
контекстным менеджером; зависимость не делает неявный commit. Запись должна явно
определить транзакцию через `with session.begin():` — успех фиксируется, ошибка откатывается.
Engine создаётся в lifespan, освобождается при остановке; импорт приложения не подключается к БД.

Синхронный SQLAlchemy выбран для прозрачности. FastAPI запускает синхронные handlers
в thread pool. AsyncSession — возможная альтернатива при обоснованной нагрузке;
это потребует async driver и дисциплины во всей цепочке вызовов.

Миграция `0001` содержит конкретные `create_table`, constraints и indexes;
она не импортирует текущие модели. Поэтому изменение Python-класса не переписывает
старую миграцию. В приложении нет `create_all()` при запуске.
`alembic upgrade head` выполняет только ещё не применённые версии.
Autogenerate помогает подготовить следующую миграцию, но её обязательно проверяют:
он не знает бизнес-смысл переименований и преобразований данных.

Деньги хранятся в `NUMERIC(12,2)` и Python `Decimal`, время — `TIMESTAMPTZ`.
PostgreSQL хранит момент времени; исходное название часового пояса не сохраняется.
У заказа есть снимок адреса и лимитов SLA, чтобы изменения профиля/договора не
меняли историю. `CHECK` запрещает отрицательные суммы, неправильное количество,
неизвестные статусы и доставку раньше получения. Сумму items и order нужно
согласовывать транзакционно в будущем сервисе записи; межтабличного CHECK здесь нет.

Readiness выполняет `SELECT 1` и чтение `orders`. Недоступная БД или неприменённая
начальная миграция дают HTTP 503 с безопасным сообщением. Это минимальная проверка,
а не полный аудит всех таблиц или совпадения каждой версии схемы.
Liveness и `/info` работают без подключения к серверу БД.

## Seed и SLA

Seed создаёт 120 customers, 24 suppliers и SLA, 60 couriers, 600 orders,
540 deliveries, 1620 delivery_events, позиции товаров и одного demo operator.
Данные полностью синтетические; email используют домен `example.test`.
Клиенты, поставщики и курьеры заказа находятся в одном городе.

Набор фиксирован через `Random(42)` и `as_of=2026-09-18T12:00:00+00:00`:

| Сценарий | Заказы |
| --- | ---: |
| Доставлены вовремя | 180 |
| Доставлены с задержкой | 180 |
| Отменены | 60 |
| Активны и просрочены на as_of | 120 |
| Активны, дедлайн ещё не наступил | 60 |

Задержки доставленных заказов: supplier/courier/address — по 60.
Нарушения SLA передачи поставщиком: 60 завершённых + 60 активных заказов.
Задержка доставки и нарушение SLA поставщика — разные показатели; их нельзя складывать.
SLA подтверждения измеряется от `created_at`, SLA передачи — от `confirmed_at`.
Отмены исключаются из расчётов активных просрочек.

Пример PostgreSQL-запроса к фактам (ожидается `120` на стандартном seed):

```sql
SELECT count(*) AS supplier_handoff_violations
FROM orders o
JOIN deliveries d ON d.order_id = o.id
WHERE o.status <> 'cancelled'
  AND coalesce(d.picked_up_at, TIMESTAMPTZ '2026-09-18 12:00:00+00')
      > o.confirmed_at + o.handoff_sla_minutes * INTERVAL '1 minute';
```

Команда seed использует одну транзакцию. PostgreSQL advisory lock сериализует
параллельные seed-запуски. Повторный запуск при наличии всех 600 demo references
ничего не изменяет, в том числе не восстанавливает вручную изменённые данные.
Непустая БД без полного набора вызывает ошибку без перезаписи.
CLI запрещает seed вне `local`/`test`. Это локальная мера предосторожности,
а не замена разграничению прав PostgreSQL.

Можно задать другой `--as-of` при первом запуске на пустой БД. Повторная команда
с новой датой не сдвигает существующие заказы. Для запроса «сегодня» в будущем demo
нужно согласовать часы приложения с датой набора или создать отдельную свежую demo-БД.

## Связь с AI Engineering

Grounding — опора ответа модели на проверяемые данные. Например, будущий tool
выполнит SQL и вернёт `supplier_handoff_violations=120`; модель должна объяснить
это число со ссылкой на данные. Сама модель число не определяет.

Evaluation — проверка AI на наборе вопросов с известным правильным результатом.
Фиксированный seed даёт такой результат: например, «Сколько активных просрочек
на дату наблюдения?» → 120. Это подготовка данных для будущей evaluation,
а не уже измеренное качество LLM.

Embeddings — числовое представление смысла текста для поиска похожих фрагментов.
Их модель, размерность и vector index выберем в фазе 5. Наличие pgvector-образа
в Compose само по себе не создаёт extension или embedding-колонку.

## Запуск

Из корня, если `.env` ещё нет: `cp -n .env.example .env`.

```bash
docker compose up --build -d postgres backend
docker compose exec backend .venv/bin/python -m app.db.seed
curl http://localhost:8000/api/v1/health/ready
```

Compose ждёт healthy PostgreSQL, затем backend применяет миграции и запускает API.
Seed запускается явно: обычный запуск приложения не добавляет demo-данные.
`docker compose up --build` запускает весь проект. Для production миграции следует
вынести в отдельный deployment step до запуска нескольких backend replicas.

Ожидаемый ответ seed на пустой БД:

```json
{"created":true,"counts":{"customers":120,"suppliers":24,"couriers":60,"orders":600,"deliveries":540,"delivery_events":1620}}
```

Повторный запуск: `created: false`, те же counts. Ожидаемый HTTP-ответ:

```json
{"status":"ready"}
```

Backend без Docker, при уже запущенном PostgreSQL:

```bash
cd backend
../.tools/bin/uv sync --locked --cache-dir ../.cache/uv
.venv/bin/alembic upgrade head
.venv/bin/python -m app.db.seed
.venv/bin/uvicorn app.main:app --reload
```

Настрой `APP_DATABASE_URL` в `.env` под свою БД. При наличии глобального uv
можно использовать `uv sync --locked`. В Compose адрес задаётся через POSTGRES_*;
при специальных символах в пароле URL нужно корректно кодировать.

## Проверки

На окружении реализации: **19 passed, 10 skipped**; Ruff и frontend build прошли.
PostgreSQL-варианты пропущены: Docker executable ссылается на отсутствующий
Docker.app, сервер PostgreSQL не найден. Полный запуск Compose и проверка
на PostgreSQL остаются непроверенными. Есть два предупреждения deprecation
из зависимостей Starlette/httpx/anyio; ошибок тестов нет.

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/alembic upgrade head --sql
```

По умолчанию реляционные тесты используют SQLite с включёнными foreign keys:
это быстрые проверки схемы, seed, ограничений и rollback. Отдельно проверяется
генерация SQL для PostgreSQL. Это не заменяет запуск на PostgreSQL.

Для интеграционных проверок на локальном PostgreSQL:

```bash
TEST_DATABASE_URL=postgresql+psycopg://copilot:copilot_local_only@localhost:5432/copilot \
  .venv/bin/pytest -q
```

Тесты создают уникальную `test_<uuid>` schema и удаляют только её после выполнения.
Используй локальную тестовую БД с правом CREATE SCHEMA. При отсутствии переменной
PostgreSQL-варианты явно помечаются skipped; они не считаются прошедшими.
Downgrade проверяется на пустой изолированной тестовой схеме. В рабочей БД
`alembic downgrade base` удаляет таблицы и данные — не использовать для обычного рестарта.

## Что важно запомнить / типичные ошибки

- `relationship()` не заменяет foreign key; «один к одному» требует UNIQUE.
- Session не следует разделять между запросами или потоками.
- `flush()` отправляет изменения в БД, `commit()` фиксирует транзакцию.
- Изменение ORM-модели не меняет уже созданную таблицу: нужна миграция.
- Сравнивай deadlines с явным моментом времени; состояние «просрочен» меняется со временем.
- Seed и настоящие пользовательские данные не нужно смешивать автоматически.

## Вопросы для собеседования

1. Чем отличаются Engine, connection pool, Session и transaction?
2. Почему миграции надёжнее `create_all()` при развитии проекта?
3. Почему статус delayed лучше вычислять из дедлайна и фактического завершения?
4. Зачем хранить SLA snapshot на order?
5. Что SQLite-тесты не доказывают о PostgreSQL?
6. Как фиксированные данные помогают оценивать точность AI?

## Домашнее задание

Напиши SELECT, который показывает число просроченных активных заказов по supplier
на `2026-09-18 12:00 UTC`. Проверь, что сумма групп равна 120, и объясни,
почему доставленные с опозданием заказы не входят в этот показатель.

Рекомендуемый commit: `feat: add database models migrations and synthetic seed`.
Следующая фаза — Basic AI, только после отдельного сообщения.

Первоисточники: [SQLAlchemy Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html),
[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
