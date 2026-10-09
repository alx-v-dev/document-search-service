from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.search.elasticsearch import (
    delete_document as delete_index_document,
    search_document_ids,
)

SEARCH_RESULT_LIMIT = 20


async def search_documents(query: str, session: AsyncSession) -> list[Document]:
    document_ids = await search_document_ids(query)
    if not document_ids:
        return []

    statement = (
        select(Document)
        .where(Document.id.in_(document_ids))
        .order_by(Document.created_date.desc())
        .limit(SEARCH_RESULT_LIMIT)
    )
    result = await session.scalars(statement)
    return list(result)


async def delete_document(document_id: int, session: AsyncSession) -> bool:
    document = await session.get(Document, document_id)
    if document is None:
        return False

    await delete_index_document(document_id)

    try:
        await session.delete(document)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return True
