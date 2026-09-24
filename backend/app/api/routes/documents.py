from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from app.rag.parsing import MAX_BYTES, invalid, validate_filename
from app.rag.service import DocumentService
from app.schemas.documents import DocumentInfo, DocumentSource, SearchRequest

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


@router.post("", response_model=DocumentInfo, status_code=201)
async def upload_document(
    request: Request,
    filename: Annotated[str, Query(min_length=1, max_length=250)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentInfo:
    """Upload raw file bytes (not multipart). Example: curl --data-binary @policy.pdf."""
    validate_filename(filename)
    data = bytearray()
    async for part in request.stream():
        if len(data) + len(part) > MAX_BYTES:
            raise invalid("Document exceeds 5 MiB", 413)
        data.extend(part)
    return await service.ingest(filename, bytes(data))


@router.get("", response_model=list[DocumentInfo])
async def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DocumentInfo]:
    return await run_in_threadpool(service.repository.list_documents, offset, limit)


@router.post("/search", response_model=list[DocumentSource])
async def search_documents(
    body: SearchRequest,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> list[DocumentSource]:
    return await service.search(body.query, body.top_k)
