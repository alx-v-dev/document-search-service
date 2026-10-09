import ast
import argparse
import asyncio
import csv
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from app.db.models import Document
from app.db.session import close_db, init_db, replace_documents
from app.search.elasticsearch import (
    bulk_index_documents,
    close_elasticsearch,
    recreate_index,
)

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
REQUIRED_COLUMNS = {"text", "created_date", "rubrics"}


def parse_rubrics(value: str, document_id: int) -> list[str]:
    try:
        rubrics = ast.literal_eval(value)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"Document {document_id}: invalid rubrics") from error

    if not isinstance(rubrics, list) or not all(
        isinstance(rubric, str) for rubric in rubrics
    ):
        raise ValueError(f"Document {document_id}: rubrics must be a list of strings")

    return rubrics


def parse_documents(path: Path) -> list[Document]:
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - fieldnames
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"CSV is missing required columns: {missing}")

        documents = []
        for document_id, row in enumerate(reader, start=1):
            try:
                created_date = datetime.strptime(
                    row["created_date"], DATETIME_FORMAT
                )
            except ValueError as error:
                raise ValueError(
                    f"Document {document_id}: invalid created_date"
                ) from error

            documents.append(
                Document(
                    id=document_id,
                    text=row["text"],
                    rubrics=parse_rubrics(row["rubrics"], document_id),
                    created_date=created_date,
                )
            )

    if not documents:
        raise ValueError("CSV contains no documents")

    return documents


async def import_documents(path: Path) -> int:
    documents = parse_documents(path)

    try:
        await init_db()
        await recreate_index()
        await replace_documents(documents)
        await bulk_index_documents((document.id, document.text) for document in documents)
    finally:
        await close_elasticsearch()
        await close_db()

    return len(documents)


def parse_arguments(args: Sequence[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Import documents from a CSV file")
    parser.add_argument("csv_path", type=Path, metavar="CSV_PATH")
    return parser.parse_args(args).csv_path


async def main(path: Path) -> None:
    imported_count = await import_documents(path)
    print(f"Imported {imported_count} documents")


if __name__ == "__main__":
    asyncio.run(main(parse_arguments()))
