import os
import uuid
from typing import Optional
from brokenvault.common.hashing import hash_bytes, hash_file_path

class CASCorruptedError(Exception):
    pass

class CASValidationError(Exception):
    pass

class ContentAddressableStore:
    def __init__(self, chunks_dir: str, staging_dir: str):
        self.chunks_dir = chunks_dir
        self.staging_dir = staging_dir

    def get_chunk_path(self, chunk_id: str) -> str:
        clean_id = chunk_id.lower().strip()
        if len(clean_id) < 4:
            return os.path.join(self.chunks_dir, clean_id)
        prefix1 = clean_id[:2]
        prefix2 = clean_id[2:4]
        return os.path.join(self.chunks_dir, prefix1, prefix2, clean_id)

    def has_chunk(self, chunk_id: str) -> bool:
        target_path = self.get_chunk_path(chunk_id)
        return os.path.isfile(target_path)

    def save_chunk(self, chunk_id: str, data: bytes) -> int:
        clean_id = chunk_id.lower().strip()
        computed_hash = hash_bytes(data)
        if computed_hash != clean_id:
            raise CASValidationError(f"Hash mismatch: expected {clean_id}, got {computed_hash}")
        
        target_path = self.get_chunk_path(clean_id)
        if os.path.isfile(target_path):
            return len(data)
        
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        temp_file = os.path.join(self.staging_dir, f"temp_{uuid.uuid4().hex}")
        with open(temp_file, "wb") as f:
            f.write(data)
        os.replace(temp_file, target_path)
        return len(data)

    def read_chunk(self, chunk_id: str) -> bytes:
        target_path = self.get_chunk_path(chunk_id)
        if not os.path.isfile(target_path):
            raise FileNotFoundError(f"Chunk {chunk_id} not found")
        with open(target_path, "rb") as f:
            return f.read()

    def verify_chunk(self, chunk_id: str) -> bool:
        target_path = self.get_chunk_path(chunk_id)
        if not os.path.isfile(target_path):
            return False
        computed = hash_file_path(target_path)
        return computed == chunk_id.lower().strip()
