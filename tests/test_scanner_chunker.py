import os
import pytest

from brokenvault.common.path_utils import normalize_relative_path, safe_join, PathSecurityError
from brokenvault.common.hashing import hash_bytes
from brokenvault.common.models import ItemType
from brokenvault.client.uploader import scan_source_directory

def test_normalize_relative_path():
    assert normalize_relative_path("a/b/c.txt") == "a/b/c.txt"
    assert normalize_relative_path("a\\b\\c.txt") == "a/b/c.txt"
    assert normalize_relative_path("./a/b/c.txt") == "a/b/c.txt"
    assert normalize_relative_path("a/b/./c.txt") == "a/b/c.txt"

def test_reject_unsafe_paths():
    with pytest.raises(PathSecurityError):
        normalize_relative_path("/root/file.txt")
    with pytest.raises(PathSecurityError):
        normalize_relative_path("../parent.txt")
    with pytest.raises(PathSecurityError):
        normalize_relative_path("a/../../parent.txt")

def test_safe_join(temp_dir):
    base = os.path.join(temp_dir, "base")
    os.makedirs(base, exist_ok=True)
    joined = safe_join(base, "folder/file.txt")
    assert joined.startswith(base)

def test_scan_nested_structure(temp_dir):
    src = os.path.join(temp_dir, "src")
    os.makedirs(src, exist_ok=True)
    
    empty_dir = os.path.join(src, "empty_dir")
    os.makedirs(empty_dir, exist_ok=True)

    nested_dir = os.path.join(src, "nested", "sub")
    os.makedirs(nested_dir, exist_ok=True)

    empty_file = os.path.join(src, "empty.txt")
    with open(empty_file, "wb") as f:
        pass

    text_file = os.path.join(nested_dir, "hello.txt")
    with open(text_file, "wb") as f:
        f.write(b"Hello BrokenVault!")

    manifest, chunk_map = scan_source_directory(src, chunk_size=1024)

    paths = {e.path: e for e in manifest.entries}
    assert "empty_dir" in paths
    assert paths["empty_dir"].type == ItemType.DIRECTORY

    assert "empty.txt" in paths
    assert paths["empty.txt"].type == ItemType.FILE
    assert paths["empty.txt"].size_bytes == 0
    assert len(paths["empty.txt"].chunk_ids) == 0

    assert "nested/sub/hello.txt" in paths
    assert paths["nested/sub/hello.txt"].type == ItemType.FILE
    assert paths["nested/sub/hello.txt"].size_bytes == 18
    assert len(paths["nested/sub/hello.txt"].chunk_ids) == 1

    expected_cid = hash_bytes(b"Hello BrokenVault!")
    assert paths["nested/sub/hello.txt"].chunk_ids[0] == expected_cid
    assert expected_cid in chunk_map
