import os
import json
from typing import Dict, List, Tuple, Optional, Callable
from pathlib import Path

from brokenvault.common.constants import DEFAULT_CHUNK_SIZE
from brokenvault.common.hashing import hash_bytes
from brokenvault.common.models import Manifest, ManifestEntry, ItemType, UploadCommitResponse
from brokenvault.common.path_utils import normalize_relative_path
from brokenvault.client.api_client import BrokenVaultAPIClient

class ChunkLocation:
    def __init__(self, file_path: str, offset: int, length: int):
        self.file_path = file_path
        self.offset = offset
        self.length = length

    def read_bytes(self) -> bytes:
        with open(self.file_path, "rb") as f:
            f.seek(self.offset)
            return f.read(self.length)

def scan_source_directory(
    source_dir: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE
) -> Tuple[Manifest, Dict[str, ChunkLocation]]:
    source_path = os.path.abspath(source_dir)
    if not os.path.isdir(source_path):
        raise ValueError(f"Source directory does not exist: {source_dir}")

    entries: List[ManifestEntry] = []
    chunk_map: Dict[str, ChunkLocation] = {}

    for root, dirs, files in os.walk(source_path):
        rel_root = os.path.relpath(root, source_path)
        
        if rel_root != "." and rel_root != "":
            norm_dir_path = normalize_relative_path(rel_root)
            stat = os.stat(root)
            entries.append(
                ManifestEntry(
                    path=norm_dir_path,
                    type=ItemType.DIRECTORY,
                    size_bytes=0,
                    mtime=stat.st_mtime,
                    chunk_ids=[]
                )
            )

        for f in files:
            full_path = os.path.join(root, f)
            rel_file = os.path.relpath(full_path, source_path)
            norm_file_path = normalize_relative_path(rel_file)
            stat = os.stat(full_path)
            file_size = stat.st_size
            mtime = stat.st_mtime

            if file_size == 0:
                entries.append(
                    ManifestEntry(
                        path=norm_file_path,
                        type=ItemType.FILE,
                        size_bytes=0,
                        mtime=mtime,
                        chunk_ids=[]
                    )
                )
                continue

            file_chunk_ids: List[str] = []
            with open(full_path, "rb") as fp:
                offset = 0
                while chunk_bytes := fp.read(chunk_size):
                    length = len(chunk_bytes)
                    cid = hash_bytes(chunk_bytes)
                    file_chunk_ids.append(cid)
                    if cid not in chunk_map:
                        chunk_map[cid] = ChunkLocation(full_path, offset, length)
                    offset += length

            entries.append(
                ManifestEntry(
                    path=norm_file_path,
                    type=ItemType.FILE,
                    size_bytes=file_size,
                    mtime=mtime,
                    chunk_ids=file_chunk_ids
                )
            )

    entries.sort(key=lambda x: x.path)
    return Manifest(entries=entries), chunk_map

def get_session_cache_path(source_dir: str) -> str:
    abs_src = os.path.abspath(source_dir)
    return os.path.join(abs_src, ".brokenvault_session")

def execute_backup(
    source_dir: str,
    server_url: str = "http://127.0.0.1:8000",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    upload_id: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> UploadCommitResponse:
    manifest, chunk_map = scan_source_directory(source_dir, chunk_size)
    source_label = os.path.basename(os.path.abspath(source_dir))
    session_file = get_session_cache_path(source_dir)

    target_upload_id = upload_id
    if not target_upload_id and os.path.isfile(session_file):
        try:
            with open(session_file, "r") as sf:
                cached_data = json.load(sf)
                target_upload_id = cached_data.get("upload_id")
        except Exception:
            target_upload_id = None

    with BrokenVaultAPIClient(base_url=server_url) as client:
        init_res = client.init_upload(
            manifest=manifest,
            source_label=source_label,
            upload_id=target_upload_id
        )
        active_upload_id = init_res.upload_id

        try:
            with open(session_file, "w") as sf:
                json.dump({"upload_id": active_upload_id, "version_id": init_res.version_id}, sf)
        except Exception:
            pass

        all_unique_cids = list(chunk_map.keys())
        missing_cids = client.get_missing_chunks(active_upload_id, all_unique_cids)

        total_missing = len(missing_cids)
        for idx, cid in enumerate(missing_cids):
            chunk_loc = chunk_map[cid]
            chunk_data = chunk_loc.read_bytes()
            client.upload_chunk(active_upload_id, cid, chunk_data)
            if progress_callback:
                progress_callback(idx + 1, total_missing, cid)

        commit_res = client.commit_upload(active_upload_id)

        if os.path.isfile(session_file):
            try:
                os.remove(session_file)
            except Exception:
                pass

        return commit_res
