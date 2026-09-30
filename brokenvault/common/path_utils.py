import os
from pathlib import PurePosixPath, Path

class PathSecurityError(ValueError):
    pass

def normalize_relative_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip()
    if cleaned.startswith("/"):
        raise PathSecurityError(f"Absolute paths not permitted: {raw_path}")
    
    parts = cleaned.split("/")
    filtered_parts = []
    for part in parts:
        if part == "..":
            raise PathSecurityError(f"Directory traversal not permitted: {raw_path}")
        if part == "." or part == "":
            continue
        filtered_parts.append(part)
    
    return "/".join(filtered_parts)

def safe_join(base_dir: str, rel_path: str) -> str:
    norm_rel = normalize_relative_path(rel_path)
    base_resolved = os.path.abspath(base_dir)
    target_resolved = os.path.abspath(os.path.join(base_resolved, norm_rel))
    if not (target_resolved == base_resolved or target_resolved.startswith(base_resolved + os.sep)):
        raise PathSecurityError(f"Path escapes base directory: {rel_path}")
    return target_resolved
