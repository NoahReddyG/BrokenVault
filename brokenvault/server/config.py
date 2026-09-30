import os
from pydantic import BaseModel

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    vault_dir: str = "./vault_data"

    @property
    def db_path(self) -> str:
        return os.path.join(self.vault_dir, "metadata.db")

    @property
    def chunks_dir(self) -> str:
        return os.path.join(self.vault_dir, "chunks")

    @property
    def staging_dir(self) -> str:
        return os.path.join(self.vault_dir, "staging")

    def ensure_directories(self) -> None:
        os.makedirs(self.vault_dir, exist_ok=True)
        os.makedirs(self.chunks_dir, exist_ok=True)
        os.makedirs(self.staging_dir, exist_ok=True)
