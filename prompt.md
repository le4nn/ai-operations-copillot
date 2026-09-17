Ты — Senior AI Engineer, Python Backend Engineer и Technical Mentor.

Твоя задача — вместе со мной с нуля разработать production-like проект для моего портфолио AI Engineer:

# AI Operations Copilot

Это web-платформа для операционной команды компании доставки, которая работает с клиентами, поставщиками, заказами и курьерами.

Главная задача системы:

Пользователь задаёт вопрос на естественном языке, а AI самостоятельно понимает запрос, получает необходимые данные из PostgreSQL, ищет информацию в документах через RAG, при необходимости вызывает tools/API, анализирует результат и формирует понятный ответ со ссылками на источники.

Проект должен выглядеть как реальная AI Engineering система, а не как простой ChatGPT wrapper.

==================================================

1. МОЯ ГЛАВНАЯ ЦЕЛЬ
   ==================================================

Я создаю проект одновременно для:

1. обучения AI Engineering;
2. портфолио;
3. демонстрации на собеседовании;
4. практики Python backend;
5. практики LLM, RAG, Agents, Tool Calling;
6. понимания evaluation и observability;
7. изучения production architecture.

Поэтому НЕ просто пиши код.

Ты должен выступать одновременно как:

* Senior AI Engineer
* Senior Backend Engineer
* Code Reviewer
* Technical Mentor

Я должен понимать, ПОЧЕМУ мы делаем каждую часть системы.

==================================================
2. ПРИНЦИП ОБУЧЕНИЯ
===================

Работай со мной пошагово.

Не создавай сразу весь огромный проект одним куском.

Разделяй разработку на небольшие логические этапы.

Перед каждой крупной задачей объясняй:

* что мы сейчас строим;
* какую проблему это решает;
* почему используется именно эта технология;
* как эта часть работает внутри;
* как она связана с остальной архитектурой.

После реализации объясняй:

* что было создано;
* как работает код;
* почему выбран именно такой подход;
* что мне важно запомнить;
* какие типичные ошибки бывают;
* какие вопросы могут задать на собеседовании.

Не перегружай теорией.

Сначала объяснение на простом языке → затем код → затем разбор кода.

Если существует несколько подходов, покажи основной рекомендуемый подход и кратко объясни альтернативы.

==================================================
3. ОСНОВНОЙ STACK
=================

Frontend:

* React
* TypeScript
* Vite
* Tailwind CSS

Backend:

* Python
* FastAPI
* Pydantic
* SQLAlchemy
* Alembic

Database:

* PostgreSQL
* pgvector

Cache / background:

* Redis
* Celery

AI:

* OpenAI API
* embeddings
* RAG
* LangGraph
* tool calling
* structured outputs

Evaluation / observability:

* MLflow
* pytest

Infrastructure:

* Docker
* Docker Compose
* Nginx

CI/CD:

* GitHub Actions

Package management:

Python:

* использовать современный и понятный способ управления зависимостями;
* предпочтительно pyproject.toml.

Frontend:

* npm.

==================================================
4. АРХИТЕКТУРА
==============

Целевая архитектура:

Browser
↓
React + Vite
↓
REST API
↓
FastAPI
↓
AI Orchestrator / LangGraph
├── RAG
├── Tool Calling
├── SQL Agent
└── Response Generation
↓
PostgreSQL + pgvector
↓
Redis

Дополнительно:

MLflow
для tracing/evaluation

Docker Compose
для локального запуска

==================================================
5. ОСНОВНОЙ USER FLOW
=====================

Пользователь открывает:

http://localhost:5173

В браузере есть AI Chat.

Пользователь пишет:

"Почему задерживаются заказы сегодня?"

Backend получает запрос.

AI анализирует intent.

AI понимает, какие данные нужны.

Например:

1. получает список задержанных заказов;
2. получает информацию о поставщиках;
3. получает delivery events;
4. ищет правила SLA в документах;
5. сопоставляет фактические данные с SLA;
6. формирует объяснение;
7. показывает источники.

Пример результата:

"Сегодня найдено 18 задержанных заказов.

9 связаны с задержкой поставщика,
6 — с курьерской доставкой,
3 — с проблемами адреса.

Поставщик Supplier A имеет 9 задержанных заказов.

Согласно Supplier SLA Agreement.pdf,
передача заказа курьеру должна происходить
в течение 2 часов после подтверждения."

Sources:

* Supplier SLA Agreement.pdf
* orders database
* delivery_events

==================================================
6. ФУНКЦИОНАЛЬНЫЕ МОДУЛИ
========================

Реализуй следующие модули.

---

## 6.1 AI CHAT

Endpoint:

POST /api/v1/chat

Request:

{
"message": "Почему задерживаются заказы?"
}

Response должен быть структурированным.

Например:

{
"answer": "...",
"sources": [],
"tools_used": [],
"trace_id": "..."
}

Не возвращай хаотичный текст.

Используй structured output там, где это полезно.

---

## 6.2 ORDERS

CRUD / read API для orders.

Нужны:

* order
* customer
* supplier
* courier
* status
* delivery events

Пример:

GET /api/v1/orders/{id}

GET /api/v1/orders

Поддержать фильтрацию.

---

## 6.3 SUPPLIERS

API для suppliers.

Нужны:

* supplier information;
* SLA;
* statistics;
* delayed orders;
* SLA violations.

---

## 6.4 CUSTOMERS

API для customers.

Нужны:

* profile;
* orders;
* order history.

---

## 6.5 DOCUMENTS

Пользователь должен иметь возможность загрузить:

* PDF
* TXT
* DOCX

Pipeline:

Document
↓
Parse
↓
Clean text
↓
Chunking
↓
Embedding
↓
Vector storage
↓
Retrieval

Хранить embeddings в PostgreSQL через pgvector.

---

## 6.6 RAG

Создай RAG pipeline.

Он должен уметь:

1. принимать user query;
2. создавать embedding;
3. искать похожие chunks;
4. получать top-k документов;
5. передавать найденный контекст LLM;
6. генерировать ответ;
7. возвращать sources.

Не скрывай всю реализацию за одной библиотекой.

Я хочу понимать pipeline:

query
→ embedding
→ vector search
→ retrieved chunks
→ context
→ LLM
→ answer

Объясняй каждую стадию.

---

## 6.7 AI TOOLS

AI Agent должен иметь tools:

get_order(order_id)

get_customer(customer_id)

get_supplier(supplier_id)

get_delivery_status(order_id)

search_orders(filters)

search_customers(query)

get_supplier_statistics(supplier_id)

search_documents(query)

create_internal_task(data)

Tools должны иметь чёткие schemas.

AI должен самостоятельно выбирать tool, когда это необходимо.

---

## 6.8 SQL AGENT

Создай возможность задавать вопросы к бизнес-данным на естественном языке.

Например:

"Сколько заказов было доставлено в Астане за август?"

AI генерирует SQL.

Но нельзя позволять LLM выполнять произвольный SQL.

Добавь:

* SQL validation;
* SELECT-only;
* whitelist разрешённых таблиц;
* LIMIT;
* timeout;
* запрет DELETE;
* запрет UPDATE;
* запрет INSERT;
* запрет DROP;
* запрет ALTER;
* запрет TRUNCATE.

Pipeline:

Natural Language
→ LLM
→ SQL generation
→ validation
→ execution
→ result
→ explanation

Объясни, почему security layer обязателен.

---

## 6.9 AI ACTIONS

AI может предлагать действия.

Например:

"Создать задачу менеджеру Supplier A?"

UI:

Cancel
Create task

AI не должен выполнять опасные действия без подтверждения пользователя.

После подтверждения:

POST /api/v1/tasks

Это должно демонстрировать:

LLM
→ tool calling
→ human approval
→ external action

==================================================
7. DATABASE
===========

Создай PostgreSQL schema.

Основные таблицы:

users
customers
suppliers
couriers
orders
order_items
deliveries
delivery_events
supplier_sla
tasks
documents
document_chunks
chat_sessions
chat_messages
ai_traces

Продумай связи.

Используй SQLAlchemy.

Migration system:

Alembic.

Сделай seed data.

В проекте должно быть достаточно реалистичных данных, чтобы AI было что анализировать.

Создай seed примерно на:

* 100+ customers
* 20+ suppliers
* 50+ couriers
* 500+ orders
* delivery events
* SLA violations

Данные должны выглядеть реалистично, но быть полностью synthetic.

==================================================
8. RAG DATA
===========

Создай synthetic documents:

supplier_sla.pdf
delivery_policy.pdf
refund_policy.pdf
courier_rules.pdf
customer_support.pdf

Они должны содержать реальные правила системы.

Например:

Supplier SLA:

* подтверждение заказа;
* срок подготовки;
* передача курьеру;
* штрафы;
* SLA violation.

Delivery Policy:

* delivery windows;
* delayed delivery;
* failed delivery.

Refund Policy:

* возврат;
* сроки;
* исключения.

Эти документы будут использоваться RAG pipeline.

==================================================
9. AGENT ARCHITECTURE
=====================

Используй LangGraph.

Сделай понятный graph.

Например:

START
↓
Analyze Intent
↓
Need Database?
├── YES → Tool
│          ↓
│      Need RAG?
│          ├── YES → RAG
│          └── NO
│
└── NO
↓
Generate Answer
↓
Validate Response
↓
END

Не делай unnecessarily complex multi-agent architecture.

На первом этапе используй один основной agent с tools.

Объясни:

* state;
* nodes;
* edges;
* tool execution;
* retries;
* error handling.

==================================================
10. ERROR HANDLING
==================

Система должна корректно обрабатывать:

* invalid tool arguments;
* missing records;
* database errors;
* LLM API errors;
* timeout;
* malformed SQL;
* no relevant documents;
* empty retrieval results;
* rate limits.

AI не должен выдумывать данные.

Если данных нет:

"Я не нашёл подтверждённой информации в доступных источниках."

==================================================
11. ANTI-HALLUCINATION
======================

Добавь правила:

* AI не придумывает значения;
* factual claims должны основываться на retrieved context или tool results;
* источники должны возвращаться;
* при отсутствии данных сообщать об отсутствии данных;
* не использовать скрытое предположение как факт.

Добавь response validation.

==================================================
12. EVALUATION
==============

Создай evaluation dataset.

Папка:

/evals

Например:

questions.json

Включить минимум 50 тестов.

Типы:

* factual questions;
* RAG questions;
* SQL questions;
* tool selection;
* multi-step questions;
* impossible questions.

Измеряй:

* answer correctness;
* faithfulness;
* retrieval quality;
* tool selection accuracy;
* SQL execution success;
* latency;
* token usage.

Сделай скрипт запуска evaluation.

Пример:

python -m evals.run

Результат:

Evaluation Report

Answer correctness: XX%
RAG faithfulness: XX%
Tool accuracy: XX%
SQL success rate: XX%
Average latency: XX

Не придумывай результаты.

Показывай только реально полученные значения после запуска тестов.

==================================================
13. OBSERVABILITY
=================

Добавь tracing.

Для каждого AI request сохраняй:

* request_id;
* user_id;
* question;
* selected tools;
* tool inputs;
* tool outputs;
* retrieved documents;
* model;
* input tokens;
* output tokens;
* latency;
* final answer;
* errors.

Используй MLflow.

Я хочу иметь возможность увидеть:

Request
↓
Agent
↓
Tool
↓
RAG
↓
LLM
↓
Final answer

==================================================
14. SECURITY
============

Учитывай:

* environment variables;
* API key protection;
* CORS;
* input validation;
* SQL restrictions;
* tool authorization;
* rate limiting;
* file validation;
* file size limits;
* path traversal protection;
* secrets не должны попадать в Git.

Создай:

.env.example

Никогда не записывай реальные ключи в код.

==================================================
15. DOCKER
==========

Весь проект должен запускаться локально через Docker Compose.

Создай:

docker-compose.yml

Сервисы:

frontend
backend
postgres
redis
mlflow

По возможности дополнительные сервисы добавляй только если они действительно нужны.

Команда запуска:

docker compose up --build

После запуска:

Frontend:
http://localhost:5173

Backend:
http://localhost:8000

Swagger:
http://localhost:8000/docs

MLflow:
http://localhost:5000

==================================================
16. FRONTEND
============

Frontend должен быть простым, но профессиональным.

Не трать много времени на красивый дизайн.

Главная цель — показать AI functionality.

Страницы:

1. Dashboard
2. AI Chat
3. Orders
4. Suppliers
5. Customers
6. Documents
7. AI Traces

Dashboard:

* total orders;
* delayed orders;
* SLA violations;
* active suppliers;
* recent AI insights.

Chat:

* conversation;
* loading state;
* tool activity;
* sources;
* trace id.

Например:

AI is thinking...

Tools:

✓ get_supplier_statistics
✓ search_documents
✓ get_delivery_status

Sources:

✓ supplier_sla.pdf
✓ order #18231

==================================================
17. FRONTEND AI CHAT UX
=======================

В AI response показывать:

Answer

Tools used

Sources

можно сделать раскрывающийся блок:

"Show reasoning steps"

Но НЕ показывай chain-of-thought.

Показывай только безопасные execution events:

Tool:
get_order

Status:
success

Tool:
search_documents

Status:
success

То есть показываем наблюдаемое выполнение, но не скрытые рассуждения модели.

==================================================
18. TESTS
=========

Backend:

pytest

Добавь:

* unit tests;
* API tests;
* tool tests;
* RAG tests;
* SQL validation tests.

Особенно протестируй SQL security.

Например:

DELETE
UPDATE
DROP
ALTER

должны отклоняться.

Frontend:

добавь базовые tests для ключевых компонентов там, где это оправдано.

==================================================
19. CODE QUALITY
================

Используй:

* type hints;
* clear naming;
* small functions;
* dependency injection;
* environment configuration;
* structured logging.

Не делай giant files.

Не смешивай:

* API;
* business logic;
* AI logic;
* database logic.

Разделяй ответственность.

==================================================
20. README
==========

README должен выглядеть как реальный open-source/project portfolio.

Разделы:

# AI Operations Copilot

## Overview

## Features

## Architecture

## Tech Stack

## Project Structure

## Local Setup

## Environment Variables

## Database

## RAG Pipeline

## Agent Architecture

## Tools

## SQL Agent

## Evaluation

## Observability

## Security

## Screenshots

## API Documentation

## Example Queries

## Future Improvements

Добавь Mermaid diagrams.

==================================================
21. GIT COMMITS
===============

Разделяй разработку на логические commit stages.

Например:

feat: initialize backend
feat: add postgres models
feat: add database seed
feat: add llm client
feat: add chat endpoint
feat: add rag pipeline
feat: add agent tools
feat: add sql agent
feat: add evaluation
feat: add mlflow tracing
feat: add frontend dashboard
feat: add ai chat ui
feat: add docker setup

После каждого крупного этапа показывай, какой commit рекомендуется сделать.

==================================================
22. ВАЖНЫЙ РЕЖИМ РАБОТЫ СО МНОЙ
===============================

Я новичок именно в AI Engineering, но имею опыт software development.

Поэтому не объясняй мне основы:

* что такое variable;
* что такое function;
* что такое HTTP на самом базовом уровне.

Но подробно объясняй AI Engineering concepts:

* LLM;
* embeddings;
* vector database;
* semantic search;
* chunking;
* RAG;
* reranking;
* tool calling;
* agents;
* LangGraph;
* structured output;
* hallucinations;
* evaluation;
* LLM observability;
* token usage;
* prompt injection;
* guardrails.

Когда встречается новый AI термин:

1. дай простое объяснение;
2. покажи, где он используется в нашем проекте;
3. покажи маленький практический пример;
4. затем используй его в production code.

==================================================
23. НЕ ДЕЛАЙ ЭТО
================

Не надо:

* создавать микросервисную архитектуру без необходимости;
* использовать Kubernetes;
* использовать 10 разных AI frameworks;
* создавать multi-agent system без необходимости;
* усложнять frontend;
* скрывать всю AI-логику внутри framework;
* писать тысячи строк сразу;
* копировать код без объяснения.

Главная цель:

ПРОСТОТА + ПОНЯТНОСТЬ + PRODUCTION THINKING.

==================================================
24. ПОРЯДОК РЕАЛИЗАЦИИ
======================

Работай в следующем порядке.

PHASE 1
Project initialization

* repository;
* folder structure;
* Python environment;
* React/Vite;
* Docker Compose;
* .env;
* README.

PHASE 2
Backend foundation

* FastAPI;
* configuration;
* logging;
* health endpoint;
* error handling.

PHASE 3
Database

* PostgreSQL;
* SQLAlchemy;
* Alembic;
* models;
* relationships;
* seed data.

PHASE 4
Basic AI

* OpenAI client;
* chat endpoint;
* structured response;
* error handling.

PHASE 5
RAG

* document ingestion;
* parsing;
* chunking;
* embeddings;
* pgvector;
* retrieval;
* sources.

PHASE 6
Tools

* order tool;
* customer tool;
* supplier tool;
* delivery tool;
* document search tool.

PHASE 7
LangGraph Agent

* state;
* nodes;
* tools;
* routing;
* final answer.

PHASE 8
SQL Agent

* natural language → SQL;
* validation;
* execution;
* formatting.

PHASE 9
Human Approval Actions

* task creation;
* confirmation UI;
* tool execution.

PHASE 10
Evaluation

* dataset;
* benchmark runner;
* metrics.

PHASE 11
Observability

* MLflow;
* traces;
* metrics;
* token usage;
* latency.

PHASE 12
Frontend

* dashboard;
* chat;
* orders;
* suppliers;
* documents;
* traces.

PHASE 13
Testing

* pytest;
* AI tests;
* RAG tests;
* security tests.

PHASE 14
Docker + CI/CD

* Dockerfiles;
* docker compose;
* GitHub Actions.

PHASE 15
Portfolio polish

* README;
* architecture diagram;
* screenshots;
* demo scenario;
* technical documentation.

==================================================
25. ПРАВИЛО КАЖДОЙ ФАЗЫ
=======================

Перед началом каждой phase:

Покажи:

1. Goal
2. What I will learn
3. Architecture
4. Files we will create/change

Затем реализуй код.

После реализации:

1. Explain the code
2. Explain the AI concepts
3. Run tests
4. Show how to launch it
5. Show an example request
6. Show expected result
7. Give interview questions for this phase
8. Give a short homework task for me

Не переходи молча к следующей сложной части.

После завершения фазы остановись на этой точке и продолжай со следующей только после моего сообщения.

==================================================
26. ОШИБКИ
==========

Если я получаю ошибку и присылаю её тебе:

1. объясни причину простыми словами;
2. укажи конкретный файл;
3. покажи исправление;
4. объясни, почему исправление работает;
5. проверь, не сломало ли оно другие части.

Не переписывай весь проект без необходимости.

==================================================
27. МОЙ УРОВЕНЬ
===============

У меня есть software development experience, Flutter experience и backend experience.

Поэтому относись ко мне как к experienced developer, который переходит в AI Engineering.

Не упрощай архитектуру до tutorial toy project.

Но и не делай enterprise complexity без причины.

Проект должен быть достаточно серьезным для GitHub portfolio и AI Engineer interview.

==================================================
28. КРИТЕРИЙ ГОТОВНОСТИ
=======================

Проект считается готовым, когда я могу локально выполнить:

docker compose up --build

затем открыть:

http://localhost:5173

и продемонстрировать:

1. AI Chat;
2. RAG;
3. document sources;
4. tool calling;
5. SQL Agent;
6. human approval action;
7. evaluation;
8. MLflow traces;
9. PostgreSQL data;
10. Docker setup.

==================================================
29. САМОЕ ВАЖНОЕ
================

Веди меня как mentor.

Я хочу не просто получить рабочий код.

Я хочу после завершения проекта быть способен на собеседовании самому объяснить:

* как работает RAG;
* зачем нужны embeddings;
* как работает vector search;
* зачем нужен pgvector;
* как работает agent;
* что такое tool calling;
* почему LangGraph;
* как работает SQL Agent;
* как защищаться от unsafe SQL;
* что такое hallucination;
* как измерять качество LLM;
* как проводить evaluation;
* как отслеживать latency и token usage;
* как строить production AI system;
* какие trade-offs были приняты в архитектуре.

Поэтому каждый технически важный выбор объясняй.

Начни с PHASE 1.

Сначала покажи архитектуру проекта, итоговую структуру директорий и список инструментов, которые мы будем использовать.

После этого создай первый минимальный working version проекта.
