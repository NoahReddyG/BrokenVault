import os
import zipfile
import pytest

from brokenvault.client.uploader import execute_backup
from brokenvault.client.restorer import execute_restore
from brokenvault.common.hashing import hash_file_path

def test_sample_datasets_v1_and_v2(temp_dir, live_server):
    guide_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    zip_v1 = os.path.join(guide_dir, "brokenvault_sample_v1.zip")
    zip_v2 = os.path.join(guide_dir, "brokenvault_sample_v2.zip")

    if not (os.path.isfile(zip_v1) and os.path.isfile(zip_v2)):
        pytest.skip("Sample zip files not found in parent directory")

    src_v1 = os.path.join(temp_dir, "sample_v1")
    src_v2 = os.path.join(temp_dir, "sample_v2")

    with zipfile.ZipFile(zip_v1, "r") as z1:
        z1.extractall(src_v1)

    with zipfile.ZipFile(zip_v2, "r") as z2:
        z2.extractall(src_v2)

    server_url = live_server["url"]
    res_v1 = execute_backup(src_v1, server_url=server_url, chunk_size=512 * 1024)
    assert res_v1.status == "completed"
    assert res_v1.uploaded_bytes > 0

    res_v2 = execute_backup(src_v2, server_url=server_url, chunk_size=512 * 1024)
    assert res_v2.status == "completed"
    assert res_v2.uploaded_bytes < res_v2.total_logical_bytes
    assert res_v2.reused_bytes > 0

    dest_v1 = os.path.join(temp_dir, "restored_v1")
    dest_v2 = os.path.join(temp_dir, "restored_v2")

    execute_restore(res_v1.version_id, dest_v1, server_url=server_url)
    execute_restore(res_v2.version_id, dest_v2, server_url=server_url)

    for root, dirs, files in os.walk(src_v1):
        rel = os.path.relpath(root, src_v1)
        if rel != "." and rel != "":
            assert os.path.isdir(os.path.join(dest_v1, rel))
        for f in files:
            orig_f = os.path.join(root, f)
            rest_f = os.path.join(dest_v1, rel, f) if rel != "." else os.path.join(dest_v1, f)
            assert os.path.isfile(rest_f)
            assert os.path.getsize(rest_f) == os.path.getsize(orig_f)
            if os.path.getsize(orig_f) > 0:
                assert hash_file_path(rest_f) == hash_file_path(orig_f)

    for root, dirs, files in os.walk(src_v2):
        rel = os.path.relpath(root, src_v2)
        if rel != "." and rel != "":
            assert os.path.isdir(os.path.join(dest_v2, rel))
        for f in files:
            orig_f = os.path.join(root, f)
            rest_f = os.path.join(dest_v2, rel, f) if rel != "." else os.path.join(dest_v2, f)
            assert os.path.isfile(rest_f)
            assert os.path.getsize(rest_f) == os.path.getsize(orig_f)
            if os.path.getsize(orig_f) > 0:
                assert hash_file_path(rest_f) == hash_file_path(orig_f)
