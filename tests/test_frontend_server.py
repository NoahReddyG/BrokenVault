import httpx


def test_frontend_routes_and_assets(live_server):
    server_url = live_server["url"]

    # 1. Test root dashboard serves HTML
    resp_root = httpx.get(f"{server_url}/")
    assert resp_root.status_code == 200
    assert "BrokenVault" in resp_root.text
    assert "<!DOCTYPE html>" in resp_root.text

    # 2. Test style.css asset
    resp_css = httpx.get(f"{server_url}/assets/style.css")
    assert resp_css.status_code == 200
    assert "BrokenVault" in resp_css.text or "body" in resp_css.text

    # 3. Test app.js asset
    resp_js = httpx.get(f"{server_url}/assets/app.js")
    assert resp_js.status_code == 200
    assert "BrokenVault" in resp_js.text or "api" in resp_js.text

    # 4. Test Swagger docs
    resp_docs = httpx.get(f"{server_url}/docs")
    assert resp_docs.status_code == 200

    # 5. Test API versions
    resp_ver = httpx.get(f"{server_url}/api/v1/versions")
    assert resp_ver.status_code == 200
    assert "versions" in resp_ver.json()

    # 6. Test API verify
    resp_verify = httpx.get(f"{server_url}/api/v1/verify")
    assert resp_verify.status_code == 200
    assert "total_chunks_checked" in resp_verify.json()


def test_direct_frontend_backup_and_restore_action(live_server, temp_dir):
    import os
    server_url = live_server["url"]

    # Prepare a source directory with sample data
    src_dir = os.path.join(temp_dir, "frontend_src")
    os.makedirs(os.path.join(src_dir, "nested"), exist_ok=True)
    with open(os.path.join(src_dir, "hello.txt"), "w") as f:
        f.write("Hello from web frontend backup!")
    with open(os.path.join(src_dir, "nested", "data.bin"), "wb") as f:
        f.write(b"Binary content chunk test: " * 500)

    # 1. Direct Frontend Backup Action
    resp_backup = httpx.post(
        f"{server_url}/api/v1/actions/backup",
        json={"source_dir": src_dir, "source_label": "web_backup_test"}
    )
    assert resp_backup.status_code == 200, resp_backup.text
    backup_data = resp_backup.json()
    assert backup_data["status"] == "completed"
    assert backup_data["uploaded_bytes"] > 0
    version_id = backup_data["version_id"]

    # 2. Verify version is visible in list
    resp_ver = httpx.get(f"{server_url}/api/v1/versions")
    assert resp_ver.status_code == 200
    versions = resp_ver.json()["versions"]
    assert any(v["version_id"] == version_id for v in versions)

    # 3. Direct Frontend Restore Action
    restore_dir = os.path.join(temp_dir, "frontend_restored")
    resp_restore = httpx.post(
        f"{server_url}/api/v1/actions/restore",
        json={"version_id": version_id, "destination_dir": restore_dir}
    )
    assert resp_restore.status_code == 200, resp_restore.text
    restore_data = resp_restore.json()
    assert restore_data["status"] == "completed"
    assert restore_data["entries_restored"] >= 2

    # 4. Verify exact content fidelity
    with open(os.path.join(restore_dir, "hello.txt"), "r") as f:
        assert f.read() == "Hello from web frontend backup!"
    with open(os.path.join(restore_dir, "nested", "data.bin"), "rb") as f:
        assert f.read() == b"Binary content chunk test: " * 500
