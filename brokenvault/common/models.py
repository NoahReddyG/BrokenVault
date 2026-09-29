from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class ItemType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"

class ManifestEntry(BaseModel):
    path: str
    type: ItemType
    size_bytes: int = 0
    mtime: float = 0.0
    chunk_ids: List[str] = Field(default_factory=list)

class Manifest(BaseModel):
    entries: List[ManifestEntry]

class UploadInitRequest(BaseModel):
    source_label: Optional[str] = None
    manifest: Manifest

class UploadInitResponse(BaseModel):
    upload_id: str
    version_id: str
    missing_chunk_ids: List[str]
    reused_chunk_ids: List[str]
    total_logical_bytes: int
    reused_bytes: int

class MissingChunksQuery(BaseModel):
    chunk_ids: List[str]

class MissingChunksResponse(BaseModel):
    missing_chunk_ids: List[str]

class UploadCommitResponse(BaseModel):
    version_id: str
    status: str
    total_logical_bytes: int
    uploaded_bytes: int
    reused_bytes: int
    created_at: str

class VersionSummary(BaseModel):
    version_id: str
    created_at: str
    total_logical_bytes: int
    uploaded_bytes: int
    reused_bytes: int
    is_completed: bool
    source_label: Optional[str] = None

class VersionListResponse(BaseModel):
    versions: List[VersionSummary]

class DamagedFileInfo(BaseModel):
    version_id: str
    path: str

class DamagedChunkInfo(BaseModel):
    chunk_id: str
    status: str
    affected_versions: List[str]
    affected_files: List[DamagedFileInfo]

class VerifyResponse(BaseModel):
    total_chunks_checked: int
    corrupted_chunks_count: int
    corrupted_chunks: List[DamagedChunkInfo]
