from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.config import get_settings
from app.db.session import close_db, init_db
from app.search.elasticsearch import close_elasticsearch, create_index

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await init_db()
        await create_index()
        yield
    finally:
        await close_elasticsearch()
        await close_db()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(documents_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
