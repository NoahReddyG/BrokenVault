import os
from brokenvault.client.uploader import execute_backup
from brokenvault.client.api_client import BrokenVaultAPIClient
from brokenvault.server.cas import ContentAddressableStore

def test_verify_detects_corrupted_chunk_and_blast_radius(temp_dir, live_server):
    src = os.path.join(temp_dir, "verify_src")
    os.makedirs(src, exist_ok=True)

    test_file = os.path.join(src, "critical_data.bin")
    with open(test_file, "wb") as f:
        f.write(b"Unique critical data payload for corruption test.")

    server_url = live_server["url"]
    backup_res = execute_backup(src, server_url=server_url, chunk_size=64 * 1024)
    assert backup_res.status == "completed"

    with BrokenVaultAPIClient(base_url=server_url) as client:
        manifest = client.get_version_manifest(backup_res.version_id)
        cid = manifest.entries[0].chunk_ids[0] if manifest.entries[0].chunk_ids else manifest.entries[1].chunk_ids[0]

        healthy_report = client.verify_storage()
        assert healthy_report.total_chunks_checked >= 1
        assert healthy_report.corrupted_chunks_count == 0

        vault_dir = live_server["vault_dir"]
        cas = ContentAddressableStore(os.path.join(vault_dir, "chunks"), os.path.join(vault_dir, "staging"))
        chunk_path = cas.get_chunk_path(cid)
        assert os.path.isfile(chunk_path)

        with open(chunk_path, "r+b") as fp:
            fp.write(b"TAMPERED_HEADER")

        damaged_report = client.verify_storage()
        assert damaged_report.corrupted_chunks_count == 1
        damaged_entry = damaged_report.corrupted_chunks[0]
        assert damaged_entry.chunk_id == cid
        assert damaged_entry.status == "CORRUPTED_HASH_MISMATCH"
        assert backup_res.version_id in damaged_entry.affected_versions
        assert any(af.path == "critical_data.bin" for af in damaged_entry.affected_files)
