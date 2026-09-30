import os
from brokenvault.client.uploader import execute_backup
from brokenvault.client.api_client import BrokenVaultAPIClient

def test_deduplication_and_reuse(temp_dir, live_server):
    src_v1 = os.path.join(temp_dir, "v1")
    os.makedirs(src_v1, exist_ok=True)

    large_binary = os.path.join(src_v1, "data.bin")
    part_a = b"A" * (256 * 1024)
    part_b = b"B" * (256 * 1024)
    with open(large_binary, "wb") as f:
        f.write(part_a + part_b)

    common_doc = os.path.join(src_v1, "doc.txt")
    with open(common_doc, "wb") as f:
        f.write(b"Common shared documentation across versions.")

    server_url = live_server["url"]
    res_v1 = execute_backup(src_v1, server_url=server_url, chunk_size=256 * 1024)

    assert res_v1.status == "completed"
    assert res_v1.uploaded_bytes > 0
    assert res_v1.reused_bytes == 0

    src_v2 = os.path.join(temp_dir, "v2")
    os.makedirs(src_v2, exist_ok=True)

    large_binary_v2 = os.path.join(src_v2, "data.bin")
    part_c = b"C" * (256 * 1024)
    with open(large_binary_v2, "wb") as f:
        f.write(part_a + part_c)

    common_doc_v2 = os.path.join(src_v2, "doc.txt")
    with open(common_doc_v2, "wb") as f:
        f.write(b"Common shared documentation across versions.")

    new_file_v2 = os.path.join(src_v2, "new.txt")
    with open(new_file_v2, "wb") as f:
        f.write(b"New file in version 2.")

    res_v2 = execute_backup(src_v2, server_url=server_url, chunk_size=256 * 1024)

    assert res_v2.status == "completed"
    assert res_v2.uploaded_bytes < res_v2.total_logical_bytes
    assert res_v2.reused_bytes > 0

    with BrokenVaultAPIClient(base_url=server_url) as client:
        versions_list = client.list_versions()
        assert len(versions_list.versions) == 2
        v_ids = [v.version_id for v in versions_list.versions]
        assert res_v1.version_id in v_ids
        assert res_v2.version_id in v_ids
