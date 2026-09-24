# PHASE 6 — Tools

Цель: предоставить будущему агенту контролируемый доступ к бизнес-данным и RAG.
Фаза реализует инструменты и их исполнение. Автоматический выбор инструментов
моделью и цикл LangGraph появятся в фазе 7. Chat пока работает как в фазе 5.

## Что вы изучаете

Tool — функция, которую агент может запросить по имени и аргументам. Например,
`get_order({"order_id": 42})` получает конкретный заказ из БД. Tool calling — процесс,
в котором модель предлагает вызов, а приложение проверяет и выполняет его.
Модель не получает соединение с БД и не пишет SQL для этих инструментов.

Schema описывает допустимые аргументы. В нашем проекте Pydantic одновременно
проверяет их и генерирует JSON Schema. `order_id` должен быть положительным int:
строка `"42"`, bool `true`, лишнее поле `sql` или неизвестный инструмент отклоняются.
Наличие JSON Schema у модели не заменяет серверную валидацию.

Поток выполнения:

```text
Tool name + arguments
  → registry allowlist
  → server-side allowed_tools
  → Pydantic validation
  → explicit SQLAlchemy SELECT / DocumentService.search
  → data + sources OR typed error
  → safe execution event in logs
```

## Созданные файлы

- `app/tools/schemas.py`: аргументы, определения tools, результат и источники.
- `app/tools/repository.py`: явные SELECT и проекции разрешённых полей.
- `app/tools/registry.py`: регистрация, разрешения, dispatch, ошибки, время выполнения.
- `app/api/routes/tools.py`: локальная проверка инструментов через HTTP.
- `tests/test_tools.py`: контракты, реальные запросы к тестовой БД, статистика и ошибки.
- `app/main.py`: сборка зависимостей; API metadata обновлены до фазы 6.

Новых зависимостей и миграций нет. Используем существующие SQLAlchemy и Pydantic:
дополнительный tool framework пока не нужен. Registry не зависит от LangGraph,
поэтому его можно тестировать отдельно и подключить к агенту в следующей фазе.

## Инструменты

| Имя | Аргументы | Результат |
| --- | --- | --- |
| `get_order` | `order_id` | Заказ, сумма строкой Decimal, SLA snapshot, до 50 позиций |
| `get_customer` | `customer_id` | ID, имя, город; история через `search_orders` |
| `get_supplier` | `supplier_id` | Профиль и текущий SLA либо null |
| `get_delivery_status` | `order_id` | Статус заказа, доставка, последние 50 событий |
| `search_orders` | Необязательные `customer_id`, `supplier_id`, `status`, `city`, `limit`, `offset` | Страница заказов с `has_more` |
| `search_customers` | `query`, необязательные `limit`, `offset` | Поиск имени по буквальной подстроке |
| `get_supplier_statistics` | `supplier_id` | Агрегаты заказов поставщика и время расчёта |
| `search_documents` | `query`, необязательный `top_k` | Фрагменты RAG с текстом и источниками |

`limit` по умолчанию 20, максимум 50; `offset` до 10000; `top_k` по умолчанию 5,
максимум 10. Поиск заказов сортируется по ID, фильтры соединяются через AND.
`has_more` определяется дополнительной строкой, а не неограниченной выгрузкой.
Это не общее количество совпадений. При конкурентных изменениях offset pagination
может смещаться; cursor pagination можно добавить при росте проекта.

В событиях доставки выбираются последние 50, затем возвращаются хронологически.
`events_has_more` и `items_has_more` явно сообщают об обрезании. Пока отдельной
пагинации позиций/событий нет. Отсутствие доставки у существующего заказа — успешный
ответ с delivery=null; отсутствие самого заказа — resource_not_found.

Не возвращаем email и адреса клиентов: для текущих вопросов достаточно ID, имени
и города. Источники формируются из фактически прочитанных записей, а не моделью.
Для агрегатов sources содержат таблицы и фильтр supplier_id вместо списка всех заказов.

## Статистика и SLA

`get_supplier_statistics` считает все заказы поставщика в их **текущем состоянии**.
Это не отчёт «за сегодня» и не восстановление исторического состояния. Поле `as_of`
показывает время сервера, используемое для открытых сроков.

- `delivered_late`: завершённая доставка позже promised_at.
- `active_overdue`: confirmed/in_transit и promised_at раньше времени сервера.
- `handoff_sla_violations`: неотменённый подтверждённый заказ, у которого время
  до фактического pickup (либо до текущего времени, если pickup отсутствует)
  превышает сохранённый на заказе handoff_sla_minutes.
- `delivered_without_timestamp`: доставленные по статусу заказы без delivered_at;
  они не выдаются за своевременно доставленные.

Ровно на границе срока нарушения нет: сравнение строгое `>`.
Изменение текущего SLA поставщика не меняет snapshot заказа и результаты по нему.
Агрегирование выполняет SQL, а не LLM и не Python-цикл по всем заказам. SQLAlchemy
подставляет значения как параметры. SQLite имеет отдельное выражение разницы дат
для тестов; production использует PostgreSQL epoch.

На `DEFAULT_AS_OF=2026-09-18T12:00:00Z` тесты суммируют результаты всех поставщиков:
600 заказов, 360 доставленных, 60 отменённых, 180 активных, 180 delivered_late,
120 active_overdue и 120 handoff_sla_violations. При реальном вызове сейчас значения
по открытым срокам могут отличаться: время движется, а seed фиксирован.

## Безопасность и ошибки

Реестр содержит только восемь функций чтения. Нельзя передать произвольное имя
Python-функции или SQL. `allowed_tools` приходит из доверенного серверного кода;
он проверяется до обработки аргументов. Модель и HTTP body не назначают себе права.
Это подготовка к tool authorization, а не реализованная пользовательская RBAC:
аутентификация пользователя и отдельная read-only роль PostgreSQL ещё не добавлены.

Маршруты `/tools` доступны только при `APP_ENVIRONMENT=local` или `test`.
Для staging/production они возвращают 403. Не публикуйте local API в интернете.

Registry возвращает `status=error` с безопасным кодом для неизвестной функции,
запрета доступа, некорректных аргументов, отсутствующей записи, ошибки БД,
таймаута или сбоя сервиса. Исходные exception messages не возвращаются наружу.
Ошибка одного вызова не превращается в выдуманный успешный результат.

Общий async deadline инструмента — 100 секунд; у embeddings остаётся свой deadline,
а у PostgreSQL — statement_timeout 5 секунд. Async timeout не может принудительно
остановить Python-код в worker thread; SQL timeout ограничивает запрос на стороне БД.
Повторных вызовов на уровне registry нет; существующий OpenAI adapter сохраняет
свою retry policy. Автоматические retries требуют различать чтение и действия.

Лог содержит tool_name, status, duration_ms, error_code и общий request_id.
Аргументы, результаты и персональные данные в tool events не логируются.
MLflow tracing будет отдельной фазой. Description/events/documents нужно считать
данными, а не инструкциями, когда подключим LLM.

## Как запустить

Из корня при установленном Docker:

```bash
docker compose up --build
# На пустой demo-БД, до загрузки документов:
docker compose exec backend .venv/bin/python -m app.db.seed
```

Если seed уже создан, повторять его не требуется. Существующие пользовательские
данные seed не удаляет. Для бизнес-tools OpenAI API key не нужен.
Для `search_documents` нужны ключ, миграция pgvector и загруженные документы фазы 5.

Без Docker, при работающей PostgreSQL:

```bash
cd backend
../.tools/bin/uv sync --locked
../.tools/bin/uv run alembic upgrade head
../.tools/bin/uv run python -m app.db.seed
../.tools/bin/uv run uvicorn app.main:app --reload
```

Swagger: http://localhost:8000/docs.

```bash
curl -sS http://localhost:8000/api/v1/tools

curl -sS http://localhost:8000/api/v1/tools/get_order/execute \
  -H 'Content-Type: application/json' -d '{"arguments":{"order_id":1}}'

curl -sS http://localhost:8000/api/v1/tools/search_orders/execute \
  -H 'Content-Type: application/json' \
  -d '{"arguments":{"status":"in_transit","city":"Астана","limit":5}}'

curl -sS http://localhost:8000/api/v1/tools/get_supplier_statistics/execute \
  -H 'Content-Type: application/json' -d '{"arguments":{"supplier_id":1}}'

curl -sS http://localhost:8000/api/v1/tools/search_documents/execute \
  -H 'Content-Type: application/json' \
  -d '{"arguments":{"query":"В какой срок возвращают деньги?","top_k":3}}'
```

Успешный результат имеет `tool_name`, `status="success"`, `data`, `sources`,
`error=null`, `duration_ms`. Например, get_order для demo ID 1 вернёт reference
`DEMO-0001` и источники `orders`/`order_items`. Время выполнения измеряется реально.

Для `{"arguments":{"order_id":true}}` ожидается HTTP 200 с результатом инструмента:

```json
{
  "tool_name": "get_order",
  "status": "error",
  "data": null,
  "sources": [],
  "error": {"code": "invalid_tool_arguments", "message": "Arguments do not match tool schema"},
  "duration_ms": 0.1
}
```

Число duration_ms здесь иллюстративное. Проверяйте status, а не только HTTP-код:
ошибки выполнения — часть контракта tools. Некорректный HTTP body получает 422,
недоступное окружение — 403 со стандартным API error envelope.

## Тестирование и разбор

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
# Опционально: отдельная PostgreSQL test-БД с правами на создание schema/extension
TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/copilot_test' .venv/bin/pytest -q
```

Проверяем реальные SELECT в SQLite и опционально PostgreSQL: фильтры, связи,
денежные значения, сортировку, SQL wildcard escaping, пустые ответы, отсутствие
записей, агрегаты seed и точные границы SLA. Проверяем запрет выполнения до вызова
handler, schemas, controlled errors, timeout, document sources и local-only API.
Отдельный тест фиксирует, что бизнес-tools выполняют только SELECT.
Mock RAG проверяет передачу источников, но не измеряет retrieval quality.

Типичные ошибки: принимать bool за ID, доверять tool name от модели без allowlist,
считать длину страницы общим количеством, выдавать пустой поиск за ошибку,
приписывать политике сведения о текущих заказах, смешивать handoff SLA и delivery SLA.

Вопросы для собеседования:

1. Чем tool calling отличается от генерации SQL моделью?
2. Почему аргументы нужно проверять даже при наличии JSON Schema?
3. Где должны проверяться разрешения: в prompt или перед handler?
4. Как передавать отсутствие записи и пустой результат поиска агенту?
5. Почему нельзя повторять write-tool так же, как SELECT, без idempotency?

Домашнее задание: выберите заказ через search_orders, получите его get_order,
get_supplier и get_delivery_status. Объясните, какие данные подтверждают задержку,
а какие лишь описывают договор. Затем передайте строковый ID и убедитесь, что
ошибка возникает до SQL.

Рекомендуемый commit: `feat: add validated read-only tools for operations and document search`.
Следующая фаза после отдельного сообщения: LangGraph Agent.
