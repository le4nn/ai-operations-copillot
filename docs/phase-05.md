# PHASE 5 — RAG

Цель: загрузить документы и получить ответ с проверяемыми фрагментами источников.
Фаза заканчивается на RAG API; автоматический выбор tools и UI документов — следующие этапы.

## Что изучаем и как работает код

RAG (Retrieval-Augmented Generation) — сначала получить релевантный контекст,
затем попросить модель ответить по нему. Это не обучение модели на наших документах.

1. `app/api/routes/documents.py` читает raw body потоково, максимум 5 MiB.
   `POST /documents?filename=...` принимает байты файла, не multipart.
2. `rag/parsing.py`: pypdf извлекает текст страниц, python-docx — абзацы и таблицы,
   TXT декодируется как UTF-8. Убираем лишние пробелы. PDF сохраняет номера страниц;
   DOCX не имеет надёжной пагинации, поэтому page_number=null.
3. Chunking делит текст на фрагменты до 1200 символов с перекрытием 200 символов.
   Перекрытие помогает сохранить смысл возле границы. Это простой character-based
   baseline, а не смысловое разбиение; таблицы и сложная вёрстка могут терять структуру.
4. `rag/embeddings.py` отправляет батчи по 32 фрагмента в `text-embedding-3-small`.
   Embedding — вектор смысла: близкие формулировки обычно получают близкие векторы.
   Размер — 1536, одинаковый для документов и вопросов. Размеры, конечность значений,
   ненулевой вектор и индексы батча проверяются. Ограничение 8000 UTF-8 байт на вход
   консервативно ограничивает число токенов, не требуя отдельного tokenizer.
5. `rag/repository.py` сохраняет документ, текст, страницы, модель и векторы одной
   транзакцией. При сбое embeddings ничего не записывается. SHA-256 + версия pipeline
   предотвращают дубли записей, в том числе при одновременной загрузке; повторная
   загрузка пока всё равно вызывает embeddings API, прежде чем обнаружить дубликат.
   Оригинальный файл не сохраняется; storage_key здесь — идентификатор содержимого.
6. При поиске вопрос превращается в embedding той же моделью. pgvector выполняет
   точный cosine-поиск, фильтрует готовые документы и embedding_model, ограничивает top-k.
   Similarity = 1 − cosine distance. Это мера близости, не вероятность правильного ответа.
7. `services/chat.py` передаёт найденные фрагменты в Responses API как JSON.
   Модель возвращает answer, supported, chunk_ids. Сервер допускает только ID из
   retrieval и формирует sources сам. Пустой retrieval не вызывает генерацию.

Пример: «Когда вернут деньги?» → embedding вопроса → фрагмент refund_policy →
«В течение 10 рабочих дней после одобрения менеджером; время банка дополнительно».
Это ожидаемый смысл ответа по demo-документу, не результат live evaluation.

## Выбор технологий и ограничения

pgvector позволяет хранить данные и векторы в одной PostgreSQL БД. Для маленького
корпуса точный поиск проще и не теряет кандидатов из-за approximate index.
При росте корпуса рассмотрим HNSW, затем reranking — повторную оценку кандидатов
более точной моделью. Сейчас ни HNSW, ни reranking не реализованы.

Миграция `0002` активирует extension и добавляет nullable embedding/model:
старые фрагменты не считаются проиндексированными и не участвуют в поиске.
Смена embedding-модели требует повторной индексации всего корпуса, даже если
размерность совпадает. SQLite служит только для relational-тестов, не vector search.

`use_documents=true` явно включает ответы только по документам. Без него сохраняется
базовый chat фазы 4. Ответ на вопрос о текущих задержках нельзя получить из политики:
для этого потребуются бизнес-tools. `tools_used` пуст, поскольку agent tools ещё нет.

Порог `APP_RAG_MIN_SIMILARITY=0.3` — стартовая эвристика, не измеренное оптимальное
значение. Подбирайте его по набору вопросов. Похожий фрагмент не обязательно содержит
ответ. Structured Outputs и проверка ID предотвращают выдуманные ссылки, но не
доказывают, что каждое утверждение логически следует из цитаты.

Документы передаются как недоверенный контекст с инструкцией игнорировать команды
внутри них. Это снижение риска prompt injection, не полная защита. Пока нет tools,
поэтому документ не может сам запустить внешнее действие.

Парсинг и синхронные DB операции выполняются в worker threads. Ingestion синхронный
с точки зрения HTTP: клиент ждёт завершения; Celery пока не нужен. Embeddings имеют
общий deadline 90 секунд, генерация — существующий chat deadline. Проверки размера
архива/PDF не заменяют изоляцию парсера от враждебных файлов: перед публичным запуском
нужны process isolation/resource limits, authentication и rate limiting. OCR не реализован.

## Запуск и проверка

Из корня, при настроенном OPENAI_API_KEY в существующем `.env`:

```bash
docker compose up --build
```

Миграции применяются при старте backend. Без Docker, с PostgreSQL и установленным pgvector:

```bash
cd backend
../.tools/bin/uv sync --locked
../.tools/bin/uv run alembic upgrade head
../.tools/bin/uv run uvicorn app.main:app --reload
```

Из корня загрузите demo PDF (текст отправляется OpenAI для embeddings):

```bash
curl -sS 'http://localhost:8000/api/v1/documents?filename=refund_policy.pdf' \
  -H 'Content-Type: application/pdf' --data-binary @documents/synthetic/refund_policy.pdf

curl -sS http://localhost:8000/api/v1/documents/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"В какой срок возвращают деньги после одобрения?","top_k":3}'

curl -sS http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"В какой срок возвращают деньги после одобрения?","use_documents":true}'
```

Ожидаемая форма ответа (ID и текст зависят от БД и генерации):

```json
{
  "answer": "Возврат инициируют в течение 10 рабочих дней после одобрения менеджером. Время обработки банком дополнительно.",
  "status": "grounded_answer",
  "sources": [{"document_id": 1, "chunk_id": 1, "filename": "refund_policy.pdf", "page_number": 1, "content": "...", "similarity": 0.7}],
  "tools_used": [],
  "trace_id": "<UUID>"
}
```

Число similarity здесь иллюстративное, не измеренное. Если подходящих данных нет,
ожидаются status=insufficient_data и пустой sources. Вопрос «Сколько возвратов было
вчера?» не должен получать число из policy.

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
# На отдельной тестовой PostgreSQL БД с разрешением создавать schemas/extensions:
TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/copilot_test' .venv/bin/pytest -q
```

Тесты используют подменённый HTTP OpenAI, не реальный ключ: парсинг, лимиты, embeddings,
ошибки API, загрузка/список, rollback, дедупликация, пустой поиск, неизвестные citations,
настоящий SDK structured output. PostgreSQL-варианты дополнительно проверяют cosine
search и миграции. Без TEST_DATABASE_URL они skipped. Это не оценка качества LLM.

## Что важно запомнить

Не смешивайте embeddings разных моделей. Не используйте top-k без обработки пустого
или нерелевантного результата. Не доверяйте источникам, которые придумала модель.
Не путайте наличие правильной ссылки с доказанной достоверностью всего ответа.
В логах есть request ID, trace ID, usage и latency; MLflow появится отдельно.

Вопросы для собеседования:

- Чем RAG отличается от fine-tuning?
- Как размер chunk и overlap влияют на retrieval и стоимость?
- Почему запрос и документы должны иметь одинаковую embedding-модель?
- Когда exact search стоит заменить HNSW?
- Почему schema validation и citation validation недостаточны против hallucinations?

Домашнее задание: загрузите refund_policy.pdf, задайте три перефразированных вопроса
и один вопрос без ответа в документе. Сравните top-3 и similarity. Запишите, какой
фрагмент подтверждает ответ; попробуйте пороги 0.2 и 0.5 и объясните различия.

Рекомендуемый commit: `feat: add document ingestion and pgvector RAG with grounded sources`.

Источники: [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings),
[pgvector SQLAlchemy](https://github.com/pgvector/pgvector-python#sqlalchemy).
