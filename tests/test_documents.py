from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock
from elasticsearch import NotFoundError
from httpx import AsyncClient

from app.db import session as db_session
from app.db.models import Document
from app.search import elasticsearch as search_store

pytestmark = pytest.mark.asyncio

SeedDocuments = Callable[[Sequence[Document]], Awaitable[None]]


async def test_search_returns_matching_documents(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    await seed_documents(
        [
            Document(
                id=1,
                text="Python async services",
                created_date=datetime(2024, 1, 1, 10, 0),
                rubrics=["backend", "python"],
            ),
            Document(
                id=2,
                text="PostgreSQL storage",
                created_date=datetime(2024, 1, 3, 10, 0),
                rubrics=["databases"],
            ),
            Document(
                id=3,
                text="Testing Python applications",
                created_date=datetime(2024, 1, 2, 10, 0),
                rubrics=["testing"],
            ),
        ]
    )

    response = await client.get("/documents/search", params={"query": "python"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 3,
            "text": "Testing Python applications",
            "created_date": "2024-01-02T10:00:00",
            "rubrics": ["testing"],
        },
        {
            "id": 1,
            "text": "Python async services",
            "created_date": "2024-01-01T10:00:00",
            "rubrics": ["backend", "python"],
        },
    ]


async def test_search_returns_empty_list_without_matches(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    await seed_documents(
        [
            Document(
                id=1,
                text="PostgreSQL storage",
                created_date=datetime(2024, 1, 1),
                rubrics=["databases"],
            )
        ]
    )

    response = await client.get("/documents/search", params={"query": "python"})

    assert response.status_code == 200
    assert response.json() == []


async def test_search_returns_twenty_newest_matching_documents(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    documents = [
        Document(
            id=document_id,
            text=f"Python document {document_id}",
            created_date=datetime(2024, 1, 1) + timedelta(days=document_id),
            rubrics=["python"],
        )
        for document_id in range(1, 26)
    ]
    documents.append(
        Document(
            id=100,
            text="PostgreSQL storage",
            created_date=datetime(2024, 2, 1),
            rubrics=["databases"],
        )
    )
    await seed_documents(documents)

    response = await client.get("/documents/search", params={"query": "python"})

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 20
    assert [document["id"] for document in results] == list(range(25, 5, -1))


async def test_search_sorts_by_created_date_descending(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    await seed_documents(
        [
            Document(
                id=30,
                text="Python middle document",
                created_date=datetime(2024, 1, 2),
                rubrics=["python"],
            ),
            Document(
                id=10,
                text="Python newest document",
                created_date=datetime(2024, 1, 3),
                rubrics=["python"],
            ),
            Document(
                id=20,
                text="Python oldest document",
                created_date=datetime(2024, 1, 1),
                rubrics=["python"],
            ),
        ]
    )

    response = await client.get("/documents/search", params={"query": "python"})

    assert response.status_code == 200
    results = response.json()
    assert [document["id"] for document in results] == [10, 30, 20]
    assert [document["created_date"] for document in results] == [
        "2024-01-03T00:00:00",
        "2024-01-02T00:00:00",
        "2024-01-01T00:00:00",
    ]


async def test_delete_removes_document_from_both_stores(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    await seed_documents(
        [
            Document(
                id=1,
                text="Python document",
                created_date=datetime(2024, 1, 1),
                rubrics=["python"],
            )
        ]
    )

    response = await client.delete("/documents/1")

    assert response.status_code == 204
    assert response.content == b""
    async with db_session.session_factory() as session:
        assert await session.get(Document, 1) is None
    with pytest.raises(NotFoundError):
        await search_store.client.get(index=search_store.INDEX_NAME, id="1")


async def test_delete_missing_document_returns_not_found(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    await seed_documents(
        [
            Document(
                id=1,
                text="Python document",
                created_date=datetime(2024, 1, 1),
                rubrics=["python"],
            )
        ]
    )

    response = await client.delete("/documents/999")

    assert response.status_code == 404
    async with db_session.session_factory() as session:
        document = await session.get(Document, 1)
        assert document is not None
        assert document.text == "Python document"
        assert document.created_date == datetime(2024, 1, 1)
        assert document.rubrics == ["python"]
    indexed_document = await search_store.client.get(
        index=search_store.INDEX_NAME, id="1"
    )
    assert indexed_document["_source"] == {"id": 1, "text": "Python document"}


async def test_deleted_document_is_absent_from_subsequent_search(
    client: AsyncClient, seed_documents: SeedDocuments
) -> None:
    await seed_documents(
        [
            Document(
                id=1,
                text="Python document to delete",
                created_date=datetime(2024, 1, 2),
                rubrics=["python"],
            ),
            Document(
                id=2,
                text="Python surviving document",
                created_date=datetime(2024, 1, 1),
                rubrics=["python"],
            ),
        ]
    )
    before_delete = await client.get(
        "/documents/search", params={"query": "python"}
    )
    assert before_delete.status_code == 200
    assert [document["id"] for document in before_delete.json()] == [1, 2]

    delete_response = await client.delete("/documents/1")
    assert delete_response.status_code == 204
    after_delete = await client.get(
        "/documents/search", params={"query": "python"}
    )

    assert after_delete.status_code == 200
    assert after_delete.json() == [
        {
            "id": 2,
            "text": "Python surviving document",
            "created_date": "2024-01-01T00:00:00",
            "rubrics": ["python"],
        }
    ]


async def test_delete_preserves_postgresql_on_elasticsearch_error(
    client: AsyncClient,
    seed_documents: SeedDocuments,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_documents(
        [
            Document(
                id=1,
                text="Python document",
                created_date=datetime(2024, 1, 1),
                rubrics=["python"],
            )
        ]
    )

    mocked_delete = AsyncMock(
        side_effect=RuntimeError("Elasticsearch unavailable")
    )
    monkeypatch.setattr(search_store.client, "delete", mocked_delete)

    with pytest.raises(RuntimeError, match="Elasticsearch unavailable"):
        await client.delete("/documents/1")

    mocked_delete.assert_awaited_once_with(
        index=search_store.INDEX_NAME,
        id="1",
    )

    async with db_session.session_factory() as session:
        document = await session.get(Document, 1)
        assert document is not None
        assert document.text == "Python document"

    indexed_document = await search_store.client.get(
        index=search_store.INDEX_NAME,
        id="1",
    )
    assert indexed_document["_source"] == {
        "id": 1,
        "text": "Python document",
    }