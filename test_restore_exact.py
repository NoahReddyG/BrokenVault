import os
import time
from brokenvault.client.uploader import execute_backup
from brokenvault.client.restorer import execute_restore
from brokenvault.common.hashing import hash_file_path

def test_exact_restore_fidelity(temp_dir, live_server):
    src = os.path.join(temp_dir, "exact_src")
    os.makedirs(src, exist_ok=True)

    empty_folder = os.path.join(src, "empty_dir")
    os.makedirs(empty_folder, exist_ok=True)

    nested_folder = os.path.join(src, "level1", "level2")
    os.makedirs(nested_folder, exist_ok=True)

    empty_f = os.path.join(src, "zero_bytes.empty")
    with open(empty_f, "wb") as f:
        pass

    text_f = os.path.join(nested_folder, "sample.txt")
    with open(text_f, "wb") as f:
        f.write(b"Exact restore verification content line 1\nLine 2")

    bin_f = os.path.join(src, "image.dat")
    with open(bin_f, "wb") as f:
        f.write(os.urandom(64 * 1024))

    fixed_mtime = time.time() - 5000.0
    os.utime(empty_f, (fixed_mtime, fixed_mtime))
    os.utime(text_f, (fixed_mtime, fixed_mtime))
    os.utime(bin_f, (fixed_mtime, fixed_mtime))

    server_url = live_server["url"]
    backup_res = execute_backup(src, server_url=server_url, chunk_size=32 * 1024)
    assert backup_res.status == "completed"

    dst = os.path.join(temp_dir, "restored_dst")
    execute_restore(backup_res.version_id, dst, server_url=server_url)

    assert os.path.isdir(os.path.join(dst, "empty_dir"))
    assert os.path.isdir(os.path.join(dst, "level1", "level2"))

    restored_empty = os.path.join(dst, "zero_bytes.empty")
    assert os.path.isfile(restored_empty)
    assert os.path.getsize(restored_empty) == 0

    restored_text = os.path.join(dst, "level1", "level2", "sample.txt")
    assert os.path.isfile(restored_text)
    with open(restored_text, "rb") as f:
        assert f.read() == b"Exact restore verification content line 1\nLine 2"

    restored_bin = os.path.join(dst, "image.dat")
    assert os.path.isfile(restored_bin)
    assert hash_file_path(restored_bin) == hash_file_path(bin_f)

    stat_orig = os.stat(text_f)
    stat_restored = os.stat(restored_text)
    assert abs(stat_orig.st_mtime - stat_restored.st_mtime) <= 1.0
