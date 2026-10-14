import io
import math
import re
from abc import ABC, abstractmethod
from collections import Counter

from app.core.config import settings
from app.models.entities import Chunk, Document
from app.services.providers import embed
from pypdf import PdfReader
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select


def parse_document(name: str, content: bytes) -> list[tuple[int, str]]:
    extension = name.rsplit(".", 1)[-1].lower()
    if extension == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 300:
            raise ValueError("Encrypted or oversized PDF")
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    elif extension in {"txt", "md", "csv"}:
        text = content.decode("utf-8")
        if "\x00" in text:
            raise ValueError("Binary content is not accepted")
        pages = [(1, text)]
    else:
        raise ValueError("Supported formats: PDF, TXT, Markdown, CSV")
    if sum(len(text) for _, text in pages) > 2_000_000:
        raise ValueError("Extracted document exceeds limit")
    if not any(text.strip() for _, text in pages):
        raise ValueError("No extractable text; scanned PDFs need OCR")
    return pages


def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    if size <= overlap or overlap < 0:
        raise ValueError("Invalid chunk settings")
    text = re.sub(r"[ \t]+", " ", text).strip()
    return [text[i : i + size] for i in range(0, len(text), size - overlap) if text[i : i + size].strip()]


def tokens(text):
    return re.findall(r"\w+", text.lower())


def lexical_rank(query, chunks):
    terms = set(tokens(query))
    counts = [Counter(tokens(chunk.text)) for chunk in chunks]
    frequency = Counter(term for count in counts for term in count)
    average = sum(sum(count.values()) for count in counts) / max(1, len(counts))
    scored = []
    for chunk, count in zip(chunks, counts):
        length = sum(count.values())
        score = sum(
            math.log(1 + (len(chunks) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            * count[term]
            * 2.2
            / (count[term] + 1.2 * (0.25 + 0.75 * length / max(1, average)))
            for term in terms
            if count[term]
        )
        if score:
            scored.append((chunk.id, score))
    return [item[0] for item in sorted(scored, key=lambda item: item[1], reverse=True)]


def fuse(rankings: list[list[str]]):
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (60 + rank + 1)
    return sorted(scores, key=lambda key: scores[key], reverse=True)


class Reranker(ABC):
    @abstractmethod
    def rank(self, query: str, candidates: list[Chunk]) -> list[Chunk]: ...


class LexicalReranker(Reranker):
    def rank(self, query, candidates):
        words = set(tokens(query))
        return sorted(
            candidates, key=lambda chunk: len(words & set(tokens(chunk.text))) / max(1, len(words)), reverse=True
        )


async def index_document(session, document: Document):
    if settings().retrieval_backend == "lexical":
        document.status = "INDEXED"
        document.error = None
        await session.commit()
        return
    client = AsyncQdrantClient(url=settings().qdrant_url)
    try:
        chunks = list((await session.scalars(select(Chunk).where(Chunk.document_id == document.id))).all())
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset : offset + 64]
            vectors = await embed([chunk.text for chunk in batch])
            if not await client.collection_exists(settings().qdrant_collection):
                await client.create_collection(
                    settings().qdrant_collection,
                    vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE),
                )
                await client.create_payload_index(
                    settings().qdrant_collection, "organization_id", models.PayloadSchemaType.KEYWORD
                )
            await client.upsert(
                settings().qdrant_collection,
                points=[
                    models.PointStruct(
                        id=chunk.id,
                        vector=vector,
                        payload={
                            "organization_id": document.organization_id,
                            "document_id": document.id,
                            "chunk_id": chunk.id,
                            "page": chunk.page,
                            "section": chunk.section,
                            "source": document.name,
                            "created_at": chunk.created_at.isoformat(),
                        },
                    )
                    for chunk, vector in zip(batch, vectors)
                ],
            )
        document.status = "INDEXED"
        document.error = None
        await session.commit()
    finally:
        await client.close()


async def retrieve(session, organization_id, query):
    chunks = list(
        (
            await session.scalars(
                select(Chunk)
                .join(Document, Document.id == Chunk.document_id)
                .where(Chunk.organization_id == organization_id, Document.status == "INDEXED")
                .limit(10000)
            )
        ).all()
    )
    if not chunks:
        return []
    if settings().retrieval_backend == "lexical":
        ranked = lexical_rank(query, chunks)
        mapping = {chunk.id: chunk for chunk in chunks}
        return [mapping[key] for key in ranked[:8]]
    vector = (await embed([query]))[0]
    client = AsyncQdrantClient(url=settings().qdrant_url)
    try:
        result = await client.query_points(
            settings().qdrant_collection,
            query=vector,
            query_filter=models.Filter(
                must=[models.FieldCondition(key="organization_id", match=models.MatchValue(value=organization_id))]
            ),
            limit=25,
        )
    finally:
        await client.close()
    mapping = {chunk.id: chunk for chunk in chunks}
    candidate_ids = fuse([[str(point.id) for point in result.points], lexical_rank(query, chunks)[:25]])
    reranked = LexicalReranker().rank(query, [mapping[key] for key in candidate_ids if key in mapping][:30])
    selected: list[Chunk] = []
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    for chunk in reranked:
        signature = chunk.text[:200]
        if signature not in seen and counts[chunk.document_id] < 3:
            selected.append(chunk)
            seen.add(signature)
            counts[chunk.document_id] += 1
        if len(selected) == 8:
            break
    return selected
