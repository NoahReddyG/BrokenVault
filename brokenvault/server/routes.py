from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends, status, Response
from fastapi.responses import StreamingResponse
import io

from brokenvault.common.models import (
    UploadInitRequest, UploadInitResponse, MissingChunksQuery,
    MissingChunksResponse, UploadCommitResponse, VersionListResponse,
    Manifest, VerifyResponse
)
from brokenvault.server.service import (
    VaultService, NotFoundError, ConflictError, CASValidationError
)

router = APIRouter(prefix="/api/v1")

def get_vault_service(request: Request) -> VaultService:
    return request.app.state.vault_service

@router.post("/uploads/init", response_model=UploadInitResponse)
def init_upload(
    payload: UploadInitRequest,
    upload_id: Optional[str] = None,
    service: VaultService = Depends(get_vault_service)
):
    try:
        return service.init_upload(
            manifest=payload.manifest,
            source_label=payload.source_label,
            upload_id=upload_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/uploads/{upload_id}/missing-chunks", response_model=MissingChunksResponse)
def get_missing_chunks(
    upload_id: str,
    payload: MissingChunksQuery,
    service: VaultService = Depends(get_vault_service)
):
    try:
        missing = service.get_missing_chunks(upload_id, payload.chunk_ids)
        return MissingChunksResponse(missing_chunk_ids=missing)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.put("/uploads/{upload_id}/chunks/{chunk_id}")
async def upload_chunk(
    upload_id: str,
    chunk_id: str,
    request: Request,
    service: VaultService = Depends(get_vault_service)
):
    try:
        data = await request.body()
        size = service.save_chunk_data(chunk_id=chunk_id, data=data)
        return {"chunk_id": chunk_id, "size_bytes": size, "status": "stored"}
    except CASValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.post("/uploads/{upload_id}/commit", response_model=UploadCommitResponse)
def commit_upload(
    upload_id: str,
    service: VaultService = Depends(get_vault_service)
):
    try:
        return service.commit_upload(upload_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/versions", response_model=VersionListResponse)
def list_versions(
    service: VaultService = Depends(get_vault_service)
):
    versions = service.list_versions()
    return VersionListResponse(versions=versions)

@router.get("/versions/{version_id}/manifest", response_model=Manifest)
def get_manifest(
    version_id: str,
    service: VaultService = Depends(get_vault_service)
):
    try:
        return service.get_version_manifest(version_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/chunks/{chunk_id}")
def get_chunk(
    chunk_id: str,
    service: VaultService = Depends(get_vault_service)
):
    try:
        data = service.get_chunk_bytes(chunk_id)
        return Response(content=data, media_type="application/octet-stream")
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/verify", response_model=VerifyResponse)
def verify_data(
    service: VaultService = Depends(get_vault_service)
):
    return service.verify_all_data()
