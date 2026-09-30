import argparse
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from brokenvault.server.config import ServerConfig
from brokenvault.server.database import Database
from brokenvault.server.cas import ContentAddressableStore
from brokenvault.server.service import VaultService
from brokenvault.server.routes import router

# Resolve the frontend directory relative to this file
_HERE = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "frontend"))


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

    @app.middleware("http")
    async def add_no_cache_header(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Mount API routes first so /api/v1/* always wins
    app.include_router(router)

    # Serve the web dashboard at "/"
    @app.get("/", response_class=FileResponse)
    def root():
        index = os.path.join(_FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        # Fallback plain-text if frontend not found
        from fastapi.responses import HTMLResponse
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>BrokenVault Server</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       background: #0f172a; color: #f8fafc; padding: 40px; display: flex; justify-content: center; }
                .card { background: #1e293b; padding: 32px; border-radius: 12px; max-width: 600px; }
                h1 { color: #38bdf8; margin-top: 0; }
                a { color: #38bdf8; font-weight: bold; }
                ul { list-style: none; padding: 0; }
                li { padding: 8px 0; border-bottom: 1px solid #334155; }
                .status { display:inline-block;padding:4px 10px;background:#10b981;color:white;border-radius:9999px;font-size:12px;font-weight:bold; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>BrokenVault Server <span class="status">ONLINE</span></h1>
                <p>Frontend dashboard not found. Ensure <code>frontend/</code> exists in the BitnBuild directory.</p>
                <ul>
                    <li><a href="/docs">Swagger API Docs</a></li>
                    <li><a href="/api/v1/versions">List Versions</a></li>
                    <li><a href="/api/v1/verify">Verify Integrity</a></li>
                </ul>
            </div>
        </body>
        </html>
        """)

    # Mount static assets (CSS, JS) — must come after specific routes
    if os.path.isdir(_FRONTEND_DIR):
        app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR), name="frontend_assets")

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
