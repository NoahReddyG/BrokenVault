import os
import io
import json
import queue
import threading
from typing import Optional, Generator
from fastapi import APIRouter, Request, HTTPException, Depends, status, Response
from fastapi.responses import StreamingResponse

from brokenvault.common.models import (
    UploadInitRequest, UploadInitResponse, MissingChunksQuery,
    MissingChunksResponse, UploadCommitResponse, VersionListResponse,
    Manifest, VerifyResponse, ItemType
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


# ─── Direct execution endpoints for Web Frontend ───────────────────────

from pydantic import BaseModel
from brokenvault.common.constants import DEFAULT_CHUNK_SIZE
from brokenvault.common.hashing import hash_bytes
from brokenvault.common.path_utils import safe_join
from brokenvault.client.uploader import scan_source_directory


class ActionBackupRequest(BaseModel):
    source_dir: str
    source_label: Optional[str] = None
    chunk_size: Optional[int] = DEFAULT_CHUNK_SIZE
    upload_id: Optional[str] = None


class ActionRestoreRequest(BaseModel):
    version_id: str
    destination_dir: str


class ActionRestoreResponse(BaseModel):
    status: str
    version_id: str
    destination_dir: str
    entries_restored: int
    total_bytes: int


@router.post("/actions/backup", response_model=UploadCommitResponse)
def run_backup_action(
    payload: ActionBackupRequest,
    service: VaultService = Depends(get_vault_service)
):
    source_path = os.path.abspath(payload.source_dir)
    if not os.path.isdir(source_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source folder does not exist or is not a directory: '{payload.source_dir}' (resolved to: '{source_path}')"
        )

    chunk_size = payload.chunk_size or DEFAULT_CHUNK_SIZE
    manifest, chunk_map = scan_source_directory(source_path, chunk_size)
    label = payload.source_label or os.path.basename(source_path)

    init_res = service.init_upload(
        manifest=manifest,
        source_label=label,
        upload_id=payload.upload_id
    )
    active_upload_id = init_res.upload_id

    missing_cids = service.get_missing_chunks(active_upload_id, list(chunk_map.keys()))
    for cid in missing_cids:
        chunk_loc = chunk_map[cid]
        chunk_bytes = chunk_loc.read_bytes()
        service.save_chunk_data(cid, chunk_bytes)

    commit_res = service.commit_upload(active_upload_id)
    return commit_res


def _sse(event_type: str, data: dict) -> str:
    """Format a single SSE frame."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/actions/backup/stream")
def run_backup_stream(
    payload: ActionBackupRequest,
    service: VaultService = Depends(get_vault_service)
):
    """SSE streaming backup. Emits per-chunk progress events for the Resumable tab."""
    source_path = os.path.abspath(payload.source_dir)
    if not os.path.isdir(source_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source folder does not exist: '{source_path}'"
        )

    chunk_size = payload.chunk_size or DEFAULT_CHUNK_SIZE

    # We scan synchronously first so we know the totals, then stream the upload phase.
    manifest, chunk_map = scan_source_directory(source_path, chunk_size)
    label = payload.source_label or os.path.basename(source_path)

    init_res = service.init_upload(
        manifest=manifest,
        source_label=label,
        upload_id=payload.upload_id
    )
    active_upload_id = init_res.upload_id

    # Compute file-level stats for the UI
    file_entries = [e for e in manifest.entries if e.type == ItemType.FILE]
    total_files = len(file_entries)
    total_bytes = sum(e.size_bytes for e in file_entries)
    total_chunks = sum(len(e.chunk_ids) for e in file_entries)

    missing_cids = set(service.get_missing_chunks(active_upload_id, list(chunk_map.keys())))
    reused_cids  = set(chunk_map.keys()) - missing_cids

    # Build a chunk→file mapping for nicer progress labels
    chunk_to_file: dict = {}
    for e in file_entries:
        for cid in e.chunk_ids:
            chunk_to_file[cid] = e.path

    q: queue.Queue = queue.Queue()

    def _worker():
        try:
            # Emit the initial "started" event
            q.put(("started", {
                "upload_id": active_upload_id,
                "version_id": init_res.version_id,
                "total_files": total_files,
                "total_chunks": total_chunks,
                "total_bytes": total_bytes,
                "new_chunks": len(missing_cids),
                "reused_chunks": len(reused_cids),
            }))

            uploaded_bytes = 0
            done_chunks = 0

            # Emit reused chunks instantly
            for cid in reused_cids:
                file_path = chunk_to_file.get(cid, "")
                done_chunks += 1
                q.put(("chunk", {
                    "chunk_id": cid[:12],
                    "file": os.path.basename(file_path),
                    "status": "reused",
                    "done_chunks": done_chunks,
                    "total_chunks": total_chunks,
                    "uploaded_bytes": uploaded_bytes,
                    "total_bytes": total_bytes,
                }))

            # Upload new chunks one by one, emitting an event per chunk
            for cid in missing_cids:
                chunk_loc = chunk_map[cid]
                chunk_bytes = chunk_loc.read_bytes()
                service.save_chunk_data(cid, chunk_bytes)
                uploaded_bytes += len(chunk_bytes)
                done_chunks += 1
                file_path = chunk_to_file.get(cid, "")
                q.put(("chunk", {
                    "chunk_id": cid[:12],
                    "file": os.path.basename(file_path),
                    "status": "uploaded",
                    "done_chunks": done_chunks,
                    "total_chunks": total_chunks,
                    "uploaded_bytes": uploaded_bytes,
                    "total_bytes": total_bytes,
                }))

            commit_res = service.commit_upload(active_upload_id)
            q.put(("done", {
                "version_id": commit_res.version_id,
                "upload_id": active_upload_id,
                "status": "completed",
                "total_logical_bytes": commit_res.total_logical_bytes,
                "uploaded_bytes": commit_res.uploaded_bytes,
                "reused_bytes": commit_res.reused_bytes,
                "created_at": commit_res.created_at,
                "total_files": total_files,
                "total_chunks": total_chunks,
            }))
        except Exception as exc:
            q.put(("error", {"message": str(exc)}))
        finally:
            q.put(None)  # sentinel

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    def _generate() -> Generator[str, None, None]:
        while True:
            item = q.get()
            if item is None:
                break
            event_type, data = item
            yield _sse(event_type, data)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/actions/restore", response_model=ActionRestoreResponse)
def run_restore_action(
    payload: ActionRestoreRequest,
    service: VaultService = Depends(get_vault_service)
):
    dest_path = os.path.abspath(payload.destination_dir)
    os.makedirs(dest_path, exist_ok=True)

    try:
        manifest = service.get_version_manifest(payload.version_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    dir_entries = [e for e in manifest.entries if e.type == ItemType.DIRECTORY]
    dir_entries.sort(key=lambda e: len(e.path.split("/")))
    for dir_entry in dir_entries:
        target_dir = safe_join(dest_path, dir_entry.path)
        os.makedirs(target_dir, exist_ok=True)

    file_entries = [e for e in manifest.entries if e.type == ItemType.FILE]
    total_bytes = 0

    for file_entry in file_entries:
        target_file = safe_join(dest_path, file_entry.path)
        parent_dir = os.path.dirname(target_file)
        os.makedirs(parent_dir, exist_ok=True)

        if file_entry.size_bytes == 0:
            with open(target_file, "wb") as f:
                pass
        else:
            with open(target_file, "wb") as f:
                for cid in file_entry.chunk_ids:
                    try:
                        chunk_bytes = service.get_chunk_bytes(cid)
                    except FileNotFoundError:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Missing chunk {cid} in vault storage"
                        )
                    computed_hash = hash_bytes(chunk_bytes)
                    if computed_hash != cid.lower().strip():
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Integrity check failed: chunk {cid} corrupted on disk"
                        )
                    f.write(chunk_bytes)
            total_bytes += file_entry.size_bytes

        if file_entry.mtime > 0:
            try:
                os.utime(target_file, (file_entry.mtime, file_entry.mtime))
            except Exception:
                pass

    for dir_entry in reversed(dir_entries):
        target_dir = safe_join(dest_path, dir_entry.path)
        if dir_entry.mtime > 0 and os.path.isdir(target_dir):
            try:
                os.utime(target_dir, (dir_entry.mtime, dir_entry.mtime))
            except Exception:
                pass

    return ActionRestoreResponse(
        status="completed",
        version_id=payload.version_id,
        destination_dir=dest_path,
        entries_restored=len(manifest.entries),
        total_bytes=total_bytes
    )
