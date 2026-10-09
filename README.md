# Document Search Service

Небольшой сервис поиска документов. Elasticsearch ищет по тексту, а PostgreSQL
хранит полные документы и их даты создания.

## Стек

- Python 3.13, FastAPI;
- PostgreSQL и SQLAlchemy async с `asyncpg`;
- Elasticsearch и `AsyncElasticsearch`;
- Docker Compose;
- pytest, pytest-asyncio и httpx.

## Требования

- Docker Desktop с Docker Compose;
- Python 3.13 — для локального запуска тестов.

## Быстрый запуск

Создайте локальный `.env` на основе шаблона. Это файл конфигурации, а не
команды PowerShell.

```powershell
Copy-Item .env.example .env
```

Для локальных тестов против сервисов Compose укажите в `.env` хостовые порты:

```env
POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@127.0.0.1:15432/document_search
ELASTICSEARCH_URL=http://127.0.0.1:19200
```

Внутри Compose приложение использует имена сервисов `postgres:5432` и
`elasticsearch:9200`; эти значения задаются в `compose.yaml`.

Соберите и запустите сервисы:

```powershell
docker compose up -d --build
docker compose ps
```

Все три сервиса должны перейти в состояние `healthy`. PostgreSQL доступен с
хоста на `15432`, Elasticsearch — на `19200`, API — на `8000`. При конфликте
порта можно задать `POSTGRES_HOST_PORT`, `ELASTICSEARCH_HOST_PORT` или
`APP_HOST_PORT` перед запуском Compose и указать те же порты в `.env` для
локальных тестов.

## Импорт CSV

Импорт не запускается автоматически: он очищает PostgreSQL и пересоздаёт
Elasticsearch-индекс. CSV передаётся явно и не входит в Docker-образ.

Для импорта исходного набора данных скачайте CSV по ссылке из ТЗ. При локальном
запуске приложения выполните:

```powershell
python -m app.import_csv C:\path\to\posts.csv
```

После запуска Compose передайте файл контейнеру только на время импорта через
read-only mount:

```powershell
docker compose run --rm --no-deps `
  -v "C:\path\to\posts.csv:/input/posts.csv:ro" `
  app python -m app.import_csv /input/posts.csv
```

В репозитории есть небольшой нейтральный пример
[`examples/sample_posts.csv`](examples/sample_posts.csv). Он не является
исходным датасетом, но позволяет проверить импорт и поиск с нуля. Для него
можно выполнить:

```powershell
docker compose run --rm --no-deps `
  -v "${PWD}\examples\sample_posts.csv:/input/posts.csv:ro" `
  app python -m app.import_csv /input/posts.csv
```

## Тесты

Поднимите Compose-сервисы и настройте `.env` на их порты. Затем в PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest
```

Тесты работают с отдельными ресурсами для каждого теста: создают уникальную
PostgreSQL-схему и Elasticsearch-индекс `test_documents_<uuid>`, а затем
удаляют их. Рабочие `public.documents` и индекс `documents` не изменяются.

## API

OpenAPI-схема сохранена в [`docs.json`](docs.json); при запущенном сервисе она
также доступна по `GET /openapi.json`.

Проверка сервиса:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Поиск:

```powershell
curl.exe --get --data-urlencode "query=python" http://127.0.0.1:8000/documents/search
```

Удаление документа:

```powershell
curl.exe -i -X DELETE http://127.0.0.1:8000/documents/1
```

Поиск сначала получает совпадающие идентификаторы из Elasticsearch, затем
полные документы из PostgreSQL. PostgreSQL сортирует результат по
`created_date DESC`; ответ ограничен 20 документами.

При удалении сервис сначала проверяет существование документа в PostgreSQL,
после чего удаляет его из Elasticsearch и только затем из PostgreSQL. Ответ
Elasticsearch `404` не считается ошибкой; другая ошибка Elasticsearch не
позволяет удалить запись из PostgreSQL.

## Ограничение

Compose-конфигурация предназначена для локальной разработки: Elasticsearch
запускается без аутентификации и TLS, а PostgreSQL использует тестовые
учётные данные. Не используйте её как production-конфигурацию.
