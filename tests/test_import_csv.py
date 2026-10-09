from pathlib import Path

from app.import_csv import parse_documents


def test_parse_documents_uses_explicit_path() -> None:
    documents = parse_documents(
        Path(__file__).parent.parent / "examples" / "sample_posts.csv"
    )

    assert len(documents) == 5
    assert documents[0].id == 1
    assert documents[0].text == "Python helps teams build readable web services."
    assert documents[0].rubrics == ["python", "backend"]
