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


def make_pdf(pages):
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_parse_pdf_keeps_page_numbers():
    pages = parse_document("report.pdf", make_pdf(["Charging access drives adoption.", "Policy incentives matter."]))
    assert [number for number, _ in pages] == [1, 2]
    assert "Charging access" in pages[0][1] and "Policy incentives" in pages[1][1]


def test_encrypted_pdf_is_rejected():
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(make_pdf(["secret"]))).pages:
        writer.add_page(page)
    writer.encrypt("owner-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="Encrypted or oversized"):
        parse_document("locked.pdf", buffer.getvalue())


def test_oversized_pdf_is_rejected():
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(301):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="Encrypted or oversized"):
        parse_document("huge.pdf", buffer.getvalue())
