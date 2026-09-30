import os
import pytest
import httpx

from brokenvault.client.uploader import scan_source_directory, execute_backup
from brokenvault.client.api_client import BrokenVaultAPIClient

def test_interrupted_upload_and_continuation(temp_dir, live_server):
    src = os.path.join(temp_dir, "interrupted_src")
    os.makedirs(src, exist_ok=True)

    f1 = os.path.join(src, "chunk1.bin")
    with open(f1, "wb") as f:
        f.write(b"1" * (128 * 1024))

    f2 = os.path.join(src, "chunk2.bin")
    with open(f2, "wb") as f:
        f.write(b"2" * (128 * 1024))

    server_url = live_server["url"]
    manifest, chunk_map = scan_source_directory(src, chunk_size=128 * 1024)
    cids = list(chunk_map.keys())
    assert len(cids) == 2

    with BrokenVaultAPIClient(base_url=server_url) as client:
        init_res = client.init_upload(manifest=manifest, source_label="interrupted_test")
        upload_id = init_res.upload_id

        first_cid = cids[0]
        client.upload_chunk(upload_id, first_cid, chunk_map[first_cid].read_bytes())

        list_before = client.list_versions()
        assert len(list_before.versions) == 0

        with pytest.raises(httpx.HTTPStatusError):
            client.get_version_manifest(init_res.version_id)

        missing_now = client.get_missing_chunks(upload_id, cids)
        assert len(missing_now) == 1
        assert missing_now[0] == cids[1]

        second_cid = cids[1]
        client.upload_chunk(upload_id, second_cid, chunk_map[second_cid].read_bytes())

        commit_res = client.commit_upload(upload_id)
        assert commit_res.status == "completed"

        list_after = client.list_versions()
        assert len(list_after.versions) == 1
        assert list_after.versions[0].version_id == commit_res.version_id
