from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.session import get_session
from app.schemas.documents import DocumentResponse
from app.services.documents import delete_document, search_documents

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/search", response_model=list[DocumentResponse])
async def search_documents_endpoint(
    query: Annotated[str, Query(min_length=1)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Document]:
    return await search_documents(query, session)


@router.delete("/{document_id}",
               status_code=status.HTTP_204_NO_CONTENT,
                responses={404: {"description": "Document not found"}},
                )
async def delete_document_endpoint(
    document_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    deleted = await delete_document(document_id, session)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
