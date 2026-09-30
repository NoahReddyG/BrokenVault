import hashlib
from typing import BinaryIO

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()

def hash_stream(stream: BinaryIO, chunk_size: int = 65536) -> str:
    hasher = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        hasher.update(chunk)
    return hasher.hexdigest().lower()

def hash_file_path(file_path: str, chunk_size: int = 65536) -> str:
    with open(file_path, "rb") as f:
        return hash_stream(f, chunk_size)
