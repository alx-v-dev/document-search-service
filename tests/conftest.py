"""Integration tests use the services in .env and isolated disposable resources.

PostgreSQL must allow CREATE SCHEMA. Tests never truncate the working table or
recreate the working Elasticsearch index. To reset the working dataset manually,
run ``python -m app.import_csv`` from the project root with the virtualenv active.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from uuid import uuid4

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.config import get_settings
from app.db import session as database
from app.db.models import Document
from app.main import app
from app.search import elasticsearch as search


async def _drop_test_schema(engine: AsyncEngine, schema_name: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(DropSchema(schema_name, cascade=True, if_exists=True))


async def _delete_test_index(url: str, index_name: str) -> None:
    # Lifespan may already have closed the application's client, even on startup
    # failure. Cleanup uses its own client and only this test's exact index name.
    async with AsyncElasticsearch(url, request_timeout=5, max_retries=0) as client:
        await client.options(ignore_status=404).indices.delete(index=index_name)


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    settings = get_settings()
    resource_name = f"test_documents_{uuid4().hex}"
    print(f"Test PostgreSQL schema and Elasticsearch index: {resource_name}")

    # Callbacks run in reverse order, and all run even if another cleanup fails.
    async with AsyncExitStack() as cleanup:
        admin_engine = create_async_engine(
            settings.postgres_dsn, connect_args={"timeout": 5}
        )
        cleanup.push_async_callback(admin_engine.dispose)

        async with admin_engine.begin() as connection:
            await connection.execute(CreateSchema(resource_name))
        cleanup.push_async_callback(_drop_test_schema, admin_engine, resource_name)

        test_engine = create_async_engine(
            settings.postgres_dsn,
            connect_args={
                "timeout": 5,
                "server_settings": {"search_path": resource_name},
            },
        )
        cleanup.push_async_callback(test_engine.dispose)

        # Never fall back to public.documents if the test schema is missing.
        async with test_engine.connect() as connection:
            current_schema = await connection.scalar(text("SELECT current_schema()"))
            assert current_schema == resource_name

        search_client = AsyncElasticsearch(
            settings.elasticsearch_url, request_timeout=5, max_retries=0
        )
        cleanup.push_async_callback(
            _delete_test_index, settings.elasticsearch_url, resource_name
        )
        cleanup.push_async_callback(search_client.close)

        monkeypatch.setattr(database, "engine", test_engine)
        monkeypatch.setattr(
            database,
            "session_factory",
            async_sessionmaker(test_engine, expire_on_commit=False),
        )
        monkeypatch.setattr(search, "client", search_client)
        monkeypatch.setattr(search, "INDEX_NAME", resource_name)

        # ASGITransport does not run startup/shutdown automatically.
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as http_client:
                yield http_client


@pytest.fixture
def seed_documents(
    client: AsyncClient,
) -> Callable[[Sequence[Document]], Awaitable[None]]:
    async def seed(documents: Sequence[Document]) -> None:
        async with database.session_factory.begin() as session:
            session.add_all(documents)
        # The existing bulk helper refreshes the test index before returning.
        await search.bulk_index_documents(
            (document.id, document.text) for document in documents
        )

    return seed
