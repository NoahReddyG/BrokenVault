import os
from typing import Optional, Callable

from brokenvault.common.hashing import hash_bytes
from brokenvault.common.models import ItemType, Manifest
from brokenvault.common.path_utils import safe_join
from brokenvault.client.api_client import BrokenVaultAPIClient

class RestoreIntegrityError(Exception):
    pass

def execute_restore(
    version_id: str,
    destination_dir: str,
    server_url: str = "http://127.0.0.1:8000",
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Manifest:
    dest_path = os.path.abspath(destination_dir)
    os.makedirs(dest_path, exist_ok=True)

    with BrokenVaultAPIClient(base_url=server_url) as client:
        manifest = client.get_version_manifest(version_id)
        
        dir_entries = [e for e in manifest.entries if e.type == ItemType.DIRECTORY]
        dir_entries.sort(key=lambda e: len(e.path.split("/")))
        for dir_entry in dir_entries:
            target_dir = safe_join(dest_path, dir_entry.path)
            os.makedirs(target_dir, exist_ok=True)

        file_entries = [e for e in manifest.entries if e.type == ItemType.FILE]
        total_files = len(file_entries)

        for idx, file_entry in enumerate(file_entries):
            target_file = safe_join(dest_path, file_entry.path)
            parent_dir = os.path.dirname(target_file)
            os.makedirs(parent_dir, exist_ok=True)

            if file_entry.size_bytes == 0:
                with open(target_file, "wb") as f:
                    pass
            else:
                with open(target_file, "wb") as f:
                    for cid in file_entry.chunk_ids:
                        chunk_bytes = client.download_chunk(cid)
                        computed_hash = hash_bytes(chunk_bytes)
                        if computed_hash != cid.lower().strip():
                            raise RestoreIntegrityError(
                                f"Corrupted chunk received during restore: expected {cid}, got {computed_hash}"
                            )
                        f.write(chunk_bytes)

            if file_entry.mtime > 0:
                try:
                    os.utime(target_file, (file_entry.mtime, file_entry.mtime))
                except Exception:
                    pass

            if progress_callback:
                progress_callback(idx + 1, total_files, file_entry.path)

        for dir_entry in reversed(dir_entries):
            target_dir = safe_join(dest_path, dir_entry.path)
            if dir_entry.mtime > 0 and os.path.isdir(target_dir):
                try:
                    os.utime(target_dir, (dir_entry.mtime, dir_entry.mtime))
                except Exception:
                    pass

        return manifest
