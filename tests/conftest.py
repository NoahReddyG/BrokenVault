import os
import shutil
import socket
import threading
import time
import pytest
import uvicorn

from brokenvault.server.config import ServerConfig
from brokenvault.server.app import create_app

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

@pytest.fixture
def temp_dir(tmp_path):
    path_str = str(tmp_path)
    yield path_str

@pytest.fixture
def live_server(tmp_path):
    port = find_free_port()
    vault_dir = str(tmp_path / "vault_data")
    config = ServerConfig(host="127.0.0.1", port=port, vault_dir=vault_dir)
    app = create_app(config)
    
    server_instance = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server_instance.run, daemon=True)
    thread.start()

    server_url = f"http://127.0.0.1:{port}"

    for _ in range(50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("127.0.0.1", port))
                break
        except Exception:
            time.sleep(0.05)

    yield {
        "url": server_url,
        "vault_dir": vault_dir,
        "config": config,
        "app": app,
        "server_instance": server_instance
    }

    server_instance.should_exit = True
    thread.join(timeout=2.0)
