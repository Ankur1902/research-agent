import pytest
from app.models.entities import Chunk
from app.rag.pipeline import LexicalReranker, chunk_text, fuse, lexical_rank, parse_document


def test_chunk_overlap():
    chunks = chunk_text("abcdefghij" * 100, 100, 20)
    assert chunks[0][-20:] == chunks[1][:20]
    assert all(len(chunk) <= 100 for chunk in chunks)
    with pytest.raises(ValueError):
        chunk_text("hello", 100, 100)


@pytest.mark.parametrize("name,content", [("a.txt", b"hello world"), ("a.md", b"# hello"), ("a.csv", b"a,b\n1,2")])
def test_parse_text_formats(name, content):
    assert parse_document(name, content)[0][0] == 1


@pytest.mark.parametrize("name,content", [("a.exe", b"x"), ("a.pdf", b"not pdf"), ("a.txt", b"\x00"), ("a.txt", b"")])
def test_invalid_documents(name, content):
    with pytest.raises(ValueError):
        parse_document(name, content)


def test_hybrid_ranking():
    chunks = [Chunk(id="a", text="electric vehicle battery market"), Chunk(id="b", text="healthcare cloud systems")]
    assert lexical_rank("electric vehicle", chunks)[0] == "a"
    assert fuse([["a", "b"], ["b"]])[0] == "b"
    assert LexicalReranker().rank("battery", list(reversed(chunks)))[0].id == "a"
