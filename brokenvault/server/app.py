import argparse
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from brokenvault.server.config import ServerConfig
from brokenvault.server.database import Database
from brokenvault.server.cas import ContentAddressableStore
from brokenvault.server.service import VaultService
from brokenvault.server.routes import router

def create_app(config: ServerConfig) -> FastAPI:
    config.ensure_directories()
    db = Database(config.db_path)
    cas = ContentAddressableStore(config.chunks_dir, config.staging_dir)
    service = VaultService(db, cas)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="BrokenVault Server", lifespan=lifespan)
    app.state.config = config
    app.state.database = db
    app.state.cas = cas
    app.state.vault_service = service
    app.include_router(router)

    @app.get("/", response_class=HTMLResponse)
    def root():
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>BrokenVault Server</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; display: flex; justify-content: center; }
                .card { background: #1e293b; padding: 32px; border-radius: 12px; max-width: 600px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
                h1 { color: #38bdf8; margin-top: 0; }
                p { line-height: 1.6; color: #94a3b8; }
                a { color: #38bdf8; text-decoration: none; font-weight: bold; }
                a:hover { text-decoration: underline; }
                ul { list-style: none; padding: 0; }
                li { padding: 8px 0; border-bottom: 1px solid #334155; }
                .status { display: inline-block; padding: 4px 10px; background: #10b981; color: white; border-radius: 9999px; font-size: 12px; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>BrokenVault Server <span class="status">ONLINE</span></h1>
                <p>The deduplicating content-addressable storage server is active and healthy.</p>
                <h3>Available Endpoints:</h3>
                <ul>
                    <li><a href="/docs">Interactive API Documentation (Swagger UI)</a></li>
                    <li><a href="/api/v1/versions">List Completed Versions (/api/v1/versions)</a></li>
                    <li><a href="/api/v1/verify">Integrity Verification Audit (/api/v1/verify)</a></li>
                </ul>
            </div>
        </body>
        </html>
        """

    return app

def main():
    parser = argparse.ArgumentParser(description="BrokenVault Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--vault-dir", default="./vault_data", help="Directory for storage vault")
    args = parser.parse_args()

    config = ServerConfig(host=args.host, port=args.port, vault_dir=args.vault_dir)
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")

if __name__ == "__main__":
    main()
