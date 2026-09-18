# PHASE 2 — Backend foundation

## Цель и результат

Backend теперь имеет устойчивый каркас для последующих бизнес- и AI-модулей:
типизированную конфигурацию, application factory, модульный router, JSON logging,
корреляцию запросов, health endpoints и единый формат ошибок.

## Архитектура

```text
Environment variables
        ↓
Pydantic Settings → create_app()
                         ↓
Request → request ID middleware → /api/v1 router → endpoint
                         ↓                         ↓
                     JSON log              exception handler
                                                   ↓
                                           error envelope
```

`main.py` только собирает приложение. `api` знает о HTTP. `core` содержит
общие технические механизмы. В PHASE 3 слой `db` будет отвечать за соединения,
а `models` — за таблицы; endpoint не будет создавать соединение самостоятельно.

## Как работает код

### Settings

`Settings` читает `APP_*` variables и сразу проверяет типы. Например,
`APP_ENVIRONMENT=prodction` завершит запуск с понятной validation error,
потому что допустимы только `local`, `test`, `staging`, `production`.
`get_settings()` кэширует объект, чтобы не перечитывать окружение на каждом запросе.
Application factory принимает готовые settings, поэтому тесты явно используют `test`.

### Logging и request ID

Каждая строка лога является JSON-объектом. Такой формат легко индексируют Loki,
Elasticsearch и облачные logging systems. Middleware принимает безопасный
`X-Request-ID` или генерирует UUID, добавляет его в response и request log.
Позже этот ID свяжет HTTP request, tool calls, SQL, retrieval и MLflow trace.

Request ID — корреляционный идентификатор, а не аутентификация. Клиент может его
передать, поэтому нельзя использовать его как доказательство личности или доступа.

### Liveness и readiness

- `/health/live`: процесс отвечает. Если endpoint не работает, orchestrator может
  перезапустить процесс.
- `/health/ready`: приложение готово обслуживать трафик. После PHASE 3 сюда войдёт
  проверка обязательного подключения к PostgreSQL.

Redis или OpenAI не следует проверять на каждом health request, пока они не нужны
для базовой готовности: внешняя сеть может сделать health endpoint медленным и
вызвать каскадные рестарты.

### Error handling

Ожидаемые ошибки наследуются от `AppError` и имеют HTTP status, машинный `code`
и безопасный `message`. Ошибки входных данных получают код `validation_error`.
Неожиданное исключение подробно логируется на сервере, а клиент видит общий текст.
Это одновременно сохраняет диагностируемость и не раскрывает пароли, SQL или stack trace.

Практический будущий пример: service не находит заказ 42 и поднимает
`ResourceNotFoundError("order", 42)`. Handler превращает его в предсказуемый JSON,
который frontend может показать пользователю.

## Почему такой подход

Pydantic Settings использует тот же validation model, что будущие request schemas.
Application factory позволяет создавать разные экземпляры приложения в тестах.
Стандартного `logging` достаточно на этом этапе; отдельную logging-библиотеку можно
добавить только при появлении конкретной потребности. Handlers централизуют HTTP
representation и не заставляют каждый endpoint вручную собирать error JSON.

Альтернатива factory — глобально настроить всё при import. Это короче, но усложняет
тестовую конфигурацию и приводит к скрытому состоянию. Альтернатива JSON logs —
человекочитаемый text format; он удобнее глазами, но хуже для поиска по полям.

## Проверка и запуск

```bash
cd backend
../.tools/bin/uv sync --locked
../.tools/bin/uv run pytest
../.tools/bin/uv run ruff check .
../.tools/bin/uv run uvicorn app.main:app --reload
```

Пример:

```bash
curl -i -H 'X-Request-ID: interview-demo-01' \
  http://localhost:8000/api/v1/health/live
```

Ожидаются HTTP 200, body `{"status":"ok"}` и response header
`X-Request-ID: interview-demo-01`. В терминале backend появится JSON log с тем же ID,
методом, path, status code и latency в миллисекундах.

Фактически выполнено для PHASE 2:

- `pytest`: 7 passed;
- `ruff check`: passed;
- `ruff format --check`: passed;
- frontend TypeScript/Vite build проверяется после синхронизации UI-контракта;
- два deprecation warnings приходят из текущего FastAPI/Starlette TestClient stack,
  тесты проходят; предупреждения не скрыты.

## Что важно запомнить

- Settings — контракт между окружением и приложением.
- Application factory делает зависимости явными и улучшает тестируемость.
- Liveness и readiness отвечают на разные операционные вопросы.
- Ошибка для клиента и диагностический log имеют разный уровень деталей.
- Request ID связывает события одного запроса, но не заменяет trace/span model.
- Structured logging в PHASE 2 готовит фундамент для observability, но ещё не
  является MLflow tracing из PHASE 11.

## Типичные ошибки

- Читать `os.getenv()` по всему проекту и получать разные defaults.
- Возвращать клиенту `str(exception)` для HTTP 500.
- Логировать API keys, Authorization headers или полный пользовательский документ.
- Проверять внешний AI API внутри liveness endpoint.
- Использовать request ID как user ID или признак авторизации.
- Разрешить CORS `*` вместе с credentials в публичной конфигурации.

## Вопросы для собеседования

1. Чем liveness отличается от readiness и что бывает при их смешивании?
2. Зачем application factory, если можно создать один глобальный `FastAPI()`?
3. Почему unexpected exception нельзя возвращать клиенту целиком?
4. Как request ID проходит через async request без глобальной переменной?
5. Чем structured logs отличаются от distributed tracing?
6. Почему configuration validation должна происходить при старте?
7. Где должна находиться бизнес-ошибка: в endpoint или service layer?

## Короткое домашнее задание

Запустите backend, выполните `curl` из примера и найдите одинаковый request ID
в header и JSON log. Затем задайте `APP_LOG_LEVEL=ERROR`, перезапустите backend
и объясните, почему completion log уровня INFO исчез.

Следующий этап после вашего сообщения — PHASE 3: PostgreSQL, SQLAlchemy, Alembic,
модели, связи и synthetic seed data.
