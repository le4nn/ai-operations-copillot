from starlette.concurrency import run_in_threadpool

from app.rag.embeddings import Embeddings
from app.rag.parsing import chunk_pages, parse_document
from app.rag.repository import DocumentRepository
from app.schemas.documents import DocumentInfo, DocumentSource


class DocumentService:
    def __init__(self, repository: DocumentRepository, embeddings: Embeddings, threshold: float):
        self.repository = repository
        self.embeddings = embeddings
        self.threshold = threshold

    async def ingest(self, filename: str, data: bytes) -> DocumentInfo:
        pages = await run_in_threadpool(parse_document, filename, data)
        chunks = chunk_pages(pages)
        vectors = await self.embeddings.embed([chunk.content for chunk in chunks])
        return await run_in_threadpool(self.repository.store, filename, data, chunks, vectors)

    async def search(self, query: str, top_k: int = 5) -> list[DocumentSource]:
        vector = (await self.embeddings.embed([query]))[0]
        return await run_in_threadpool(self.repository.search, vector, top_k, self.threshold)
