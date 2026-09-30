from typing import List, Optional
import httpx

from brokenvault.common.models import (
    Manifest, UploadInitRequest, UploadInitResponse,
    MissingChunksQuery, MissingChunksResponse, UploadCommitResponse,
    VersionListResponse, VerifyResponse
)

class BrokenVaultAPIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def init_upload(self, manifest: Manifest, source_label: Optional[str] = None, upload_id: Optional[str] = None) -> UploadInitResponse:
        url = "/api/v1/uploads/init"
        params = {}
        if upload_id:
            params["upload_id"] = upload_id
        payload = UploadInitRequest(manifest=manifest, source_label=source_label)
        resp = self.client.post(url, json=payload.model_dump(), params=params)
        resp.raise_for_status()
        return UploadInitResponse.model_validate(resp.json())

    def get_missing_chunks(self, upload_id: str, chunk_ids: List[str]) -> List[str]:
        url = f"/api/v1/uploads/{upload_id}/missing-chunks"
        payload = MissingChunksQuery(chunk_ids=chunk_ids)
        resp = self.client.post(url, json=payload.model_dump())
        resp.raise_for_status()
        data = MissingChunksResponse.model_validate(resp.json())
        return data.missing_chunk_ids

    def upload_chunk(self, upload_id: str, chunk_id: str, data: bytes):
        url = f"/api/v1/uploads/{upload_id}/chunks/{chunk_id}"
        headers = {"Content-Type": "application/octet-stream"}
        resp = self.client.put(url, content=data, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def commit_upload(self, upload_id: str) -> UploadCommitResponse:
        url = f"/api/v1/uploads/{upload_id}/commit"
        resp = self.client.post(url)
        resp.raise_for_status()
        return UploadCommitResponse.model_validate(resp.json())

    def list_versions(self) -> VersionListResponse:
        url = "/api/v1/versions"
        resp = self.client.get(url)
        resp.raise_for_status()
        return VersionListResponse.model_validate(resp.json())

    def get_version_manifest(self, version_id: str) -> Manifest:
        url = f"/api/v1/versions/{version_id}/manifest"
        resp = self.client.get(url)
        resp.raise_for_status()
        return Manifest.model_validate(resp.json())

    def download_chunk(self, chunk_id: str) -> bytes:
        url = f"/api/v1/chunks/{chunk_id}"
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.content

    def verify_storage(self) -> VerifyResponse:
        url = "/api/v1/verify"
        resp = self.client.get(url)
        resp.raise_for_status()
        return VerifyResponse.model_validate(resp.json())
