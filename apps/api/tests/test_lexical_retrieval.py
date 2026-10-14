from app.core.config import settings
from app.core.db import Session
from app.models.entities import Chunk, Document, Organization
from app.rag import pipeline


async def test_lexical_index_and_retrieval_need_no_embedding_and_filter_tenants(monkeypatch):
    monkeypatch.setattr(settings(), "retrieval_backend", "lexical")

    def prohibited_network(*args, **kwargs):
        raise AssertionError("Lexical retrieval must not access embeddings or Qdrant")

    monkeypatch.setattr(pipeline, "embed", prohibited_network)
    monkeypatch.setattr(pipeline, "AsyncQdrantClient", prohibited_network)
    async with Session() as session:
        owners = [Organization(name="Tenant A"), Organization(name="Tenant B")]
        session.add_all(owners)
        await session.flush()
        for owner in owners:
            document = Document(
                organization_id=owner.id,
                name="Policy",
                content_hash=owner.id,
                text="Approval is required before execution",
            )
            session.add(document)
            await session.flush()
            session.add(Chunk(organization_id=owner.id, document_id=document.id, text=document.text, page=1))
            await session.commit()
            await pipeline.index_document(session, document)
            assert document.status == "INDEXED"
        result = await pipeline.retrieve(session, owners[0].id, "approval policy")
        assert len(result) == 1 and result[0].organization_id == owners[0].id
