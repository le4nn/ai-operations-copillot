"""Short synchronous transactions, called in worker threads by async services."""

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.ai import Document, DocumentChunk
from app.rag.embeddings import MODEL
from app.rag.parsing import CONTENT_TYPES, Chunk, validate_filename
from app.schemas.documents import DocumentInfo, DocumentSource


class DocumentRepository:
    def __init__(self, factory: sessionmaker[Session]):
        self.factory = factory

    def store(
        self, filename: str, data: bytes, chunks: list[Chunk], vectors: list[list[float]]
    ) -> DocumentInfo:
        key = sha256(data).hexdigest() + ":rag-v1"
        try:
            with self.factory() as session, session.begin():
                existing = session.scalar(select(Document).where(Document.storage_key == key))
                if existing:
                    return DocumentInfo.model_validate(existing)
                document = Document(
                    filename=filename,
                    storage_key=key,
                    content_type=CONTENT_TYPES[validate_filename(filename)],
                    status="ready",
                )
                session.add(document)
                session.flush()
                session.add_all(
                    [
                        DocumentChunk(
                            document_id=document.id,
                            chunk_index=i,
                            content=chunk.content,
                            page_number=chunk.page_number,
                            embedding=vector,
                            embedding_model=MODEL,
                        )
                        for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                    ]
                )
                return DocumentInfo.model_validate(document)
        except IntegrityError:
            # A concurrent identical upload may have won the unique storage key race.
            with self.factory() as session:
                existing = session.scalar(select(Document).where(Document.storage_key == key))
                if existing:
                    return DocumentInfo.model_validate(existing)
            raise

    def list_documents(self, offset: int, limit: int) -> list[DocumentInfo]:
        with self.factory() as session:
            return [
                DocumentInfo.model_validate(d)
                for d in session.scalars(
                    select(Document).order_by(Document.id).offset(offset).limit(limit)
                )
            ]

    def search(self, vector: list[float], top_k: int, threshold: float) -> list[DocumentSource]:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        statement = (
            select(DocumentChunk, Document.filename, distance.label("distance"))
            .join(Document)
            .where(
                Document.status == "ready",
                DocumentChunk.embedding_model == MODEL,
                DocumentChunk.embedding.is_not(None),
                distance <= 1 - threshold,
            )
            .order_by(distance, DocumentChunk.id)
            .limit(top_k)
        )
        with self.factory() as session:
            return [
                DocumentSource(
                    document_id=c.document_id,
                    chunk_id=c.id,
                    filename=name,
                    page_number=c.page_number,
                    content=c.content,
                    similarity=max(-1.0, min(1.0, 1 - float(d))),
                )
                for c, name, d in session.execute(statement)
            ]
