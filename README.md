# AI Operations Copilot

Учебный portfolio-проект AI Engineer: помощник операционной команды доставки,
который будет отвечать на вопросы по бизнес-данным и документам с источниками.

## Status / Features

**PHASE 3: database.** Добавлены SQLAlchemy-модели 15 таблиц, связи и ограничения,
миграция Alembic, сессии PostgreSQL, readiness с проверкой БД и synthetic seed:
120 клиентов, 24 поставщика, 60 курьеров, 600 заказов и 1620 событий доставки.
Доступны React-страница, FastAPI, settings, JSON-логи, request ID, единый
формат ошибок, Swagger и конфигурация пяти сервисов Docker Compose.
AI, RAG, tracing и бизнес-страницы ещё не реализованы.
Разработка идёт по одной фазе с разбором; требования — в [prompt.md](prompt.md).

## Architecture

Сейчас: Browser → Vite / React → `/api` proxy → FastAPI → SQLAlchemy → PostgreSQL.
Alembic управляет схемой; отдельная seed-команда создаёт demo-данные.

Целевая архитектура: React → FastAPI → LangGraph → tools / SQL / RAG →
PostgreSQL + pgvector. Redis + Celery обслуживают фоновые задачи;
MLflow хранит AI traces и результаты evaluation.

Backend остаётся одним приложением с разделёнными модулями. Docker-сервисы
инфраструктуры не означают, что бизнес-логику нужно делить на микросервисы.

## Tech Stack

Сейчас: Python 3.12, uv, FastAPI/Pydantic, SQLAlchemy 2, Alembic, psycopg 3,
PostgreSQL, pytest, Ruff;
React 19, TypeScript, Vite, Tailwind CSS, npm; Docker Compose.

Следующие фазы: embeddings/pgvector, Redis/Celery,
OpenAI API, LangGraph, MLflow, Nginx, GitHub Actions.
Python-зависимости фиксируются в `backend/uv.lock`, JS — в `frontend/package-lock.json`.

## Project Structure

```text
backend/
  app/api/             # routers и HTTP endpoints
  app/core/            # settings, logging, middleware, errors
  app/db/              # engine, session dependency, seed
  app/models/          # ORM-модели бизнес-данных и AI persistence
  app/main.py          # application factory и ASGI entry point
  alembic/             # история изменений схемы
  alembic.ini
  tests/               # проверки API, миграций и данных
  pyproject.toml       # зависимости и настройки Python
  uv.lock              # зафиксированные зависимости
  Dockerfile
frontend/
  src/                 # React и стили
  vite.config.ts       # плагины и proxy к backend
  package-lock.json
  Dockerfile
documents/             # будущие synthetic документы
evals/                 # будущий evaluation dataset и runner
docs/                  # архитектура, этапы и объяснения
infra/                 # будущая конфигурация Nginx
docker-compose.yml
.env.example
```

В последующих фазах `backend/app` получит `schemas`, `services`, `ai`.
Frontend получит `pages`, `components`, `api`; CI — `.github/workflows`.
Создаём эти модули по мере появления реализации.

## Local Setup

### Docker Compose

Нужен Docker с Compose v2 (например Docker Desktop). Из корня:

```bash
# Только если .env ещё не создан:
cp -n .env.example .env
docker compose config --quiet
docker compose up --build
```

После готовности backend в другом терминале:

```bash
docker compose exec backend .venv/bin/python -m app.db.seed
```

Миграции применяются перед стартом API. Seed запускается явно и повторно не
добавляет те же данные. Он требует пустую БД или уже существующий полный demo-набор.

Адреса: frontend http://localhost:5173, backend http://localhost:8000/api/v1/info,
Swagger http://localhost:8000/docs, MLflow http://localhost:5000.
Остановка: `docker compose down`. Named volumes сохраняют данные между запусками.
На macOS порт 5000 может занимать AirPlay Receiver: при конфликте измените
host port MLflow на `5001` и откройте `http://localhost:5001`.

Compose пока предназначен для локальной разработки: frontend использует Vite dev
server, MLflow — SQLite. Образы версионированы тегами, но не digest;
полностью воспроизводимый production deployment будет отдельной задачей PHASE 14.

### Без Docker: frontend + backend

Нужны Python 3.12, uv и Node.js 22.12+ (Node 20.19+ также подходит текущему каркасу).
Для работы с данными и успешного readiness нужен PostgreSQL.
Redis и MLflow пока не участвуют в обработке запросов.

```bash
cd backend
uv sync --locked
uv run alembic upgrade head
uv run python -m app.db.seed
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

В другом терминале:

```bash
cd frontend
npm ci
npm run dev
```

Если `uv` не установлен глобально, из корня проекта можно создать локальный инструмент:

```bash
python3 -m venv .tools
.tools/bin/python -m pip install uv==0.10.9
cd backend
../.tools/bin/uv sync --locked
../.tools/bin/uv run alembic upgrade head
../.tools/bin/uv run python -m app.db.seed
../.tools/bin/uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Environment Variables

| Variable | Назначение |
| --- | --- |
| `POSTGRES_DB` | Имя локальной БД в Compose |
| `POSTGRES_USER` | Локальный пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | Локальный пароль; пример не подходит для production |
| `BACKEND_URL` | Адрес API для Vite proxy; в Docker переопределён на `http://backend:8000` |
| `APP_ENVIRONMENT` | Окружение: `local`, `test`, `staging` или `production` |
| `APP_LOG_LEVEL` | Минимальный уровень структурированных логов |
| `APP_CORS_ORIGINS` | Разрешённые browser origins в формате JSON array |
| `APP_DATABASE_URL` | SQLAlchemy URL PostgreSQL; локально localhost, в Compose postgres |
| `TEST_DATABASE_URL` | Опциональная локальная тестовая PostgreSQL БД для интеграционных тестов |
| `OPENAI_API_KEY` | Зарезервирован для PHASE 4, пока не читается приложением |

`.env` не попадает в Git. Не помещайте секреты в `VITE_*`: такие переменные
доступны браузеру. Backend валидирует настройки при старте через Pydantic Settings.

## API Documentation

Swagger: http://localhost:8000/docs. Проверки backend foundation:

```bash
curl http://localhost:8000/api/v1/info
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
```

Ожидаемый ответ:

```json
{"name":"AI Operations Copilot","version":"0.3.0","environment":"local","phase":3,"status":"ready"}
```

`live` проверяет доступность процесса. `ready` сообщает, может ли приложение
обслуживать запросы: выполняет SQL и проверяет доступность таблицы orders.
Без БД или миграции возвращает HTTP 503. `/info` показывает метаданные сервиса,
его `status` не заменяет проверку `/health/ready`.
Каждый HTTP-ответ получает `X-Request-ID`; тот же ID включается в JSON-логи и ошибки.

Ошибки имеют стабильный envelope:

```json
{
  "error": {
    "code": "resource_not_found",
    "message": "order with id '42' was not found",
    "request_id": "..."
  }
}
```

Неожиданные исключения логируются с деталями на сервере, но клиент получает
безопасное сообщение без stack trace и секретов.

## Tests

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

```bash
cd frontend
npm run build
```

Backend-тесты проверяют API contracts, health semantics, request ID, публичные
ошибки, отсутствие утечки внутренних деталей, JSON formatter, миграции, seed,
связи, ограничения и rollback. Без `TEST_DATABASE_URL` PostgreSQL-проверки
помечены skipped; SQLite и offline PostgreSQL DDL не заменяют интеграционный запуск.
TypeScript и Vite проверяются production-сборкой; это не заменяет browser tests.

## Database

Compose использует PostgreSQL 17 с доступным pgvector. Alembic создаёт 15 таблиц;
SQLAlchemy работает через psycopg. `CREATE EXTENSION vector`, embedding-колонки
и поиск появятся в фазе 5. Само наличие образа не активирует extension в базе.

Seed фиксирован на `2026-09-18T12:00:00Z`: 180 доставок вовремя, 180 с задержкой,
60 отмен, 120 активных просроченных и 60 активных непросроченных заказов.
SLA поставщика и задержка доставки рассчитываются отдельно по временным меткам.
Время — TIMESTAMPTZ, деньги — NUMERIC; лимиты SLA сохраняются на заказе.
Разбор схемы, SQL-примеры и PostgreSQL-тесты — в [docs/phase-03.md](docs/phase-03.md).

## RAG Pipeline

План PHASE 5: parse → clean → chunks → embeddings → pgvector → retrieval → answer + sources.
RAG — получение подходящих фрагментов документов перед генерацией ответа.
Например, вопрос о сроке возврата должен найти пункт refund policy и сослаться на него.

## Agent Architecture / Tools / SQL Agent

PHASE 6–8: один LangGraph agent, инструменты с Pydantic schemas,
SQL validation и отдельная роль БД с ограниченными правами.
Tool calling — модель запрашивает вызов функции, а backend проверяет аргументы и выполняет её.
Например, `get_order(order_id=42)` получает реальную запись вместо догадки модели.
Создание задач потребует подтверждения пользователя в PHASE 9.

## Evaluation / Observability

PHASE 10–11: минимум 50 тестовых вопросов, измеренные метрики, MLflow traces.
Сейчас MLflow только описан как сервис; приложение ещё не отправляет traces.
Никаких результатов оценки пока нет.

## Security

Локальные порты Compose привязаны к loopback. Секреты исключены из Git и Docker
build contexts. Vite proxy позволяет frontend обращаться к `/api` через один origin.
Аутентификация, роли, rate limiting, file validation и защита SQL будут добавляться
в соответствующих фазах. Текущий каркас не предназначен для публичного deployment.

## Screenshots

Будут добавлены после реализации рабочих экранов; демонстрационные данные сейчас не показываются.

## Example Queries

Будущие демонстрационные запросы: «Почему задерживаются заказы сегодня?»,
«Какой SLA у поставщика?», «Сколько заказов доставлено в Астане за август?».
На текущем этапе chat endpoint отсутствует.

## Future Improvements

Разбор текущего этапа: [docs/phase-03.md](docs/phase-03.md).
Предыдущие этапы: [phase-01](docs/phase-01.md), [phase-02](docs/phase-02.md).
Рекомендуемый commit: `feat: add database models migrations and synthetic seed`.
