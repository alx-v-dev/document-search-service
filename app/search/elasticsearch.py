from collections.abc import Iterable

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

from app.config import get_settings

INDEX_NAME = "documents"
MAX_MATCHING_DOCUMENTS = 10_000

INDEX_MAPPING = {
    "properties": {
        "id": {"type": "integer"},
        "text": {"type": "text", "analyzer": "russian"},
    }
}

settings = get_settings()
client = AsyncElasticsearch(settings.elasticsearch_url)


async def create_index() -> None:
    if not await client.indices.exists(index=INDEX_NAME):
        await client.indices.create(index=INDEX_NAME, mappings=INDEX_MAPPING)


async def recreate_index() -> None:
    if await client.indices.exists(index=INDEX_NAME):
        await client.indices.delete(index=INDEX_NAME)
    await client.indices.create(index=INDEX_NAME, mappings=INDEX_MAPPING)


async def index_document(document_id: int, text: str) -> None:
    await client.index(
        index=INDEX_NAME,
        id=str(document_id),
        document={"id": document_id, "text": text},
    )


async def bulk_index_documents(documents: Iterable[tuple[int, str]]) -> None:
    actions = (
        {
            "_op_type": "index",
            "_index": INDEX_NAME,
            "_id": str(document_id),
            "_source": {"id": document_id, "text": text},
        }
        for document_id, text in documents
    )
    await async_bulk(client, actions, chunk_size=250)
    await client.indices.refresh(index=INDEX_NAME)


async def search_document_ids(query: str) -> list[int]:
    response = await client.search(
        index=INDEX_NAME,
        query={"match": {"text": query}},
        size=MAX_MATCHING_DOCUMENTS,
        source=False,
    )
    return [int(hit["_id"]) for hit in response["hits"]["hits"]]


async def delete_document(document_id: int) -> bool:
    try:
        await client.delete(index=INDEX_NAME, id=str(document_id))
    except NotFoundError:
        return False
    return True


async def close_elasticsearch() -> None:
    await client.close()
