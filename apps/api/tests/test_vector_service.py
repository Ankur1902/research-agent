"""Integration against Qdrant using labeled, injected test embeddings."""

import os
import uuid

import pytest
from app.core.config import settings
from app.core.db import Session
from app.models.entities import Chunk, Document, Organization
from app.rag import pipeline
from qdrant_client import AsyncQdrantClient


@pytest.mark.skipif(not os.environ.get("QDRANT_INTEGRATION"), reason="Requires real Qdrant service; run in Compose")
async def test_vector_index_retrieval_and_tenant_filter(monkeypatch):
    config = settings()
    monkeypatch.setattr(config, "qdrant_collection", f"test_{uuid.uuid4().hex}")

    async def fixture_embeddings(texts):
        return [[1.0, 0.0, 0.0] for text in texts]

    monkeypatch.setattr(pipeline, "embed", fixture_embeddings)
    client = AsyncQdrantClient(url=config.qdrant_url)
    try:
        async with Session() as session:
            organizations = [Organization(name="Vector test A"), Organization(name="Vector test B")]
            session.add_all(organizations)
            await session.flush()
            for org in organizations:
                doc = Document(
                    organization_id=org.id,
                    name="fixture.txt",
                    content_hash=uuid.uuid4().hex,
                    text="electric vehicle battery evidence",
                )
                session.add(doc)
                await session.flush()
                session.add(Chunk(organization_id=org.id, document_id=doc.id, text=doc.text, page=2))
                await session.commit()
                await pipeline.index_document(session, doc)
                assert doc.status == "INDEXED"
            chunks = await pipeline.retrieve(session, organizations[0].id, "electric battery")
            assert len(chunks) == 1
            assert chunks[0].organization_id == organizations[0].id
            assert chunks[0].page == 2
    finally:
        if await client.collection_exists(config.qdrant_collection):
            await client.delete_collection(config.qdrant_collection)
        await client.close()
