# PHASE 1 — Project initialization

## Цель и результат

Создать общий каркас, в котором frontend может обратиться к backend,
а зависимости и локальная инфраструктура описаны в репозитории.
Это основа, на которую поэтапно добавим AI, данные и проверки качества.

## Как это работает

1. React при открытии страницы вызывает `/api/v1/info`.
2. Vite принимает запрос на порту 5173 и перенаправляет его в FastAPI.
3. FastAPI возвращает Pydantic-модель `ServiceInfo` как JSON.
4. Страница показывает реальный результат запроса или сообщение об ошибке.

В контейнере `localhost` означает сам контейнер. Поэтому Vite в Compose использует
`http://backend:8000`: `backend` — DNS-имя сервиса во внутренней сети Compose.
При запуске без контейнеров proxy использует `http://localhost:8000`.
Не нужно выдавать браузеру внутреннее имя `backend`.

`pyproject.toml` описывает допустимые зависимости; `uv.lock` фиксирует выбранные версии.
`uv sync --locked` проверяет согласованность файлов. `.venv` изолирует Python-пакеты.
`package-lock.json` и `npm ci` выполняют аналогичную роль для frontend.
Lock-файлы нужно коммитить; окружения, кэши и секреты — нет.

Dockerfile описывает один образ; Compose описывает взаимодействие сервисов,
порты, volumes и настройки. PostgreSQL/Redis/MLflow пока не связаны с кодом backend:
их конфигурация готовит окружение к следующим этапам.

FastAPI выбран из заданного стека: типизированные схемы пригодятся как для HTTP,
так и для AI tool arguments. uv выбран ради единого workflow окружения и lock-файла;
альтернатива — pip + venv с отдельным инструментом фиксации зависимостей.
Tailwind подключён официальным Vite-плагином, дополнительных UI frameworks нет.

## AI concepts

На этом этапе модель не вызывается и токены не расходуются.
LLM — модель, которая генерирует текст по контексту. Сама по себе она не знает
актуальное содержимое нашей базы: фраза «заказ 42 задержан» требует результата
запроса к БД. Позже инструменты дадут модели данные, RAG — фрагменты документов,
а evaluation проверит, правильно ли система использует эти сведения.

Практический принцип уже сейчас: сообщение «API подключён» появляется только
после успешного запроса с проверкой ответа. Такой же подход к подтверждению
фактов нужен будущему AI, хотя его проверка значительно сложнее.

## Проверка и запуск

Команды запуска, тестов и пример API-запроса находятся в README.
`GET /api/v1/info` должен вернуть status `scaffold`, phase `1`.
В браузере ожидается «API подключён · Phase 1» при доступном backend.
Если backend выключен, показывается ошибка вместо фиктивного успеха.

## Фактически выполненные проверки

17 сентября 2026:

- `pytest`: 1 passed. Два deprecation warnings из Starlette/httpx/AnyIO;
  они не подавлены и не мешают проверке.
- `ruff check` и `ruff format --check`: успешно.
- `npm run build`: TypeScript и Vite build успешно.
- npm при установке сообщил `found 0 vulnerabilities`.
- Реальный HTTP-запрос к `localhost:8000/api/v1/info`: ожидаемый JSON.
- Тот же запрос через `localhost:5173/api/v1/info`: ожидаемый JSON;
  Vite proxy работает. Корневая страница отдаёт HTML.
- `.env`, `.tools`, `.cache`, `.venv` исключены из Git.

Docker/Compose не установлен в текущей среде: container build, `compose config`
и запуск пяти сервисов не проверены. Browser rendering не проверялся.
После установки Docker выполните команды Compose из README.

## Типичные ошибки

- Путать `localhost` хоста с `localhost` контейнера.
- Коммитить `.env` или передавать API-ключ в переменную `VITE_*`.
- Считать успешную сборку доказательством корректного запуска контейнеров.
- Считать наличие MLflow-сервера готовой observability: код ещё должен отправлять traces.
- Принимать работающий API за работающую AI-систему: данные и evaluation ещё впереди.

## Вопросы для собеседования

1. Чем lock-файл отличается от диапазонов зависимостей в pyproject.toml?
2. Почему браузер не должен обращаться к `http://backend:8000` напрямую?
3. Чем Docker image отличается от Compose service и volume?
4. Почему ключ OpenAI должен находиться на backend?
5. Почему даже корректный JSON от модели не гарантирует истинность ответа?

## Короткое домашнее задание

Запустите frontend и backend. Найдите `/api/v1/info` в Network браузера.
Остановите backend, обновите страницу и объясните, почему изменился статус.

## Следующие фазы

2. Backend: settings, logging, health, errors.
3. Database: SQLAlchemy, Alembic, schema, seed.
4. Basic AI: OpenAI client, structured chat response.
5. RAG: ingestion, chunks, embeddings, retrieval.
6. Typed tools.
7. LangGraph orchestration.
8. Safe SQL agent.
9. Human approval actions.
10. Evaluation dataset and runner.
11. MLflow traces.
12. Business frontend screens.
13. Extended tests and security checks.
14. Production Docker setup and CI/CD.
15. Portfolio documentation, diagrams, screenshots and demo.

После PHASE 1 останавливаемся и ждём следующего сообщения пользователя,
как предписывает prompt.md. Рекомендуемый commit: `feat: initialize project scaffold`.
