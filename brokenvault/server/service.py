import os
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Set

from brokenvault.common.models import (
    Manifest, ManifestEntry, ItemType, UploadInitResponse,
    UploadCommitResponse, VersionSummary, VerifyResponse,
    DamagedChunkInfo, DamagedFileInfo
)
from brokenvault.server.database import Database
from brokenvault.server.cas import ContentAddressableStore, CASValidationError

class ServiceError(Exception):
    pass

class NotFoundError(ServiceError):
    pass

class ConflictError(ServiceError):
    pass

class VaultService:
    def __init__(self, db: Database, cas: ContentAddressableStore):
        self.db = db
        self.cas = cas

    def init_upload(self, manifest: Manifest, source_label: Optional[str] = None, upload_id: Optional[str] = None) -> UploadInitResponse:
        now_str = datetime.now(timezone.utc).isoformat()
        
        all_chunk_ids = []
        total_logical_bytes = 0
        for entry in manifest.entries:
            if entry.type == ItemType.FILE:
                total_logical_bytes += entry.size_bytes
                all_chunk_ids.extend(entry.chunk_ids)
        
        unique_chunks = sorted(list(set(all_chunk_ids)))
        missing_chunk_ids = []
        reused_chunk_ids = []
        reused_bytes = 0

        chunk_sizes = {}
        for entry in manifest.entries:
            if entry.type == ItemType.FILE and len(entry.chunk_ids) == 1:
                chunk_sizes[entry.chunk_ids[0]] = entry.size_bytes

        for cid in unique_chunks:
            if self.cas.has_chunk(cid):
                reused_chunk_ids.append(cid)
                if cid in chunk_sizes:
                    reused_bytes += chunk_sizes[cid]
                else:
                    target_path = self.cas.get_chunk_path(cid)
                    if os.path.isfile(target_path):
                        reused_bytes += os.path.getsize(target_path)
            else:
                missing_chunk_ids.append(cid)

        with self.db.transaction() as conn:
            if upload_id:
                row = conn.execute("SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)).fetchone()
                if row:
                    version_id = row["version_id"]
                    conn.execute(
                        "UPDATE upload_sessions SET manifest_json = ?, updated_at = ? WHERE upload_id = ?",
                        (manifest.model_dump_json(), now_str, upload_id)
                    )
                    conn.execute(
                        "UPDATE versions SET total_logical_bytes = ?, reused_bytes = ? WHERE version_id = ?",
                        (total_logical_bytes, reused_bytes, version_id)
                    )
                    return UploadInitResponse(
                        upload_id=upload_id,
                        version_id=version_id,
                        missing_chunk_ids=missing_chunk_ids,
                        reused_chunk_ids=reused_chunk_ids,
                        total_logical_bytes=total_logical_bytes,
                        reused_bytes=reused_bytes
                    )

            target_upload_id = upload_id or f"up_{uuid.uuid4().hex}"
            target_version_id = f"v_{uuid.uuid4().hex[:12]}"
            
            conn.execute(
                "INSERT INTO versions (version_id, source_label, created_at, total_logical_bytes, uploaded_bytes, reused_bytes, is_completed) VALUES (?, ?, ?, ?, 0, ?, 0)",
                (target_version_id, source_label, now_str, total_logical_bytes, reused_bytes)
            )
            conn.execute(
                "INSERT INTO upload_sessions (upload_id, version_id, manifest_json, status, created_at, updated_at) VALUES (?, ?, ?, 'staged', ?, ?)",
                (target_upload_id, target_version_id, manifest.model_dump_json(), now_str, now_str)
            )

        return UploadInitResponse(
            upload_id=target_upload_id,
            version_id=target_version_id,
            missing_chunk_ids=missing_chunk_ids,
            reused_chunk_ids=reused_chunk_ids,
            total_logical_bytes=total_logical_bytes,
            reused_bytes=reused_bytes
        )

    def get_missing_chunks(self, upload_id: str, chunk_ids: List[str]) -> List[str]:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT upload_id FROM upload_sessions WHERE upload_id = ?", (upload_id,)).fetchone()
            if not row:
                raise NotFoundError(f"Upload session {upload_id} not found")

        missing = []
        for cid in chunk_ids:
            if not self.cas.has_chunk(cid):
                missing.append(cid)
        return missing

    def save_chunk_data(self, chunk_id: str, data: bytes) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        size = self.cas.save_chunk(chunk_id, data)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chunks (chunk_id, size_bytes, created_at) VALUES (?, ?, ?)",
                (chunk_id.lower().strip(), size, now_str)
            )
        return size

    def commit_upload(self, upload_id: str) -> UploadCommitResponse:
        with self.db.transaction() as conn:
            session_row = conn.execute("SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)).fetchone()
            if not session_row:
                raise NotFoundError(f"Upload session {upload_id} not found")
            
            version_id = session_row["version_id"]
            version_row = conn.execute("SELECT * FROM versions WHERE version_id = ?", (version_id,)).fetchone()
            if version_row["is_completed"] == 1:
                return UploadCommitResponse(
                    version_id=version_id,
                    status="completed",
                    total_logical_bytes=version_row["total_logical_bytes"],
                    uploaded_bytes=version_row["uploaded_bytes"],
                    reused_bytes=version_row["reused_bytes"],
                    created_at=version_row["created_at"]
                )

            manifest_data = json.loads(session_row["manifest_json"])
            manifest = Manifest.model_validate(manifest_data)

            all_cids = set()
            for entry in manifest.entries:
                if entry.type == ItemType.FILE:
                    for cid in entry.chunk_ids:
                        all_cids.add(cid.lower().strip())

            missing = [cid for cid in all_cids if not self.cas.has_chunk(cid)]
            if missing:
                raise ConflictError(f"Cannot commit: missing {len(missing)} chunks")

            conn.execute("DELETE FROM version_files WHERE version_id = ?", (version_id,))
            conn.execute("DELETE FROM file_chunks WHERE version_id = ?", (version_id,))

            for entry in manifest.entries:
                conn.execute(
                    "INSERT INTO version_files (version_id, path, type, size_bytes, mtime) VALUES (?, ?, ?, ?, ?)",
                    (version_id, entry.path, entry.type.value, entry.size_bytes, entry.mtime)
                )
                if entry.type == ItemType.FILE:
                    for idx, cid in enumerate(entry.chunk_ids):
                        conn.execute(
                            "INSERT INTO file_chunks (version_id, path, chunk_order, chunk_id) VALUES (?, ?, ?, ?)",
                            (version_id, entry.path, idx, cid.lower().strip())
                        )

            distinct_chunks = list(all_cids)
            total_uploaded_bytes = 0
            total_reused_bytes = 0

            for cid in distinct_chunks:
                target_path = self.cas.get_chunk_path(cid)
                c_size = os.path.getsize(target_path) if os.path.isfile(target_path) else 0
                prior_ref = conn.execute(
                    "SELECT 1 FROM file_chunks fc JOIN versions v ON fc.version_id = v.version_id WHERE fc.chunk_id = ? AND v.version_id != ? AND v.is_completed = 1 LIMIT 1",
                    (cid, version_id)
                ).fetchone()
                if prior_ref:
                    total_reused_bytes += c_size
                else:
                    total_uploaded_bytes += c_size

            conn.execute(
                "UPDATE versions SET is_completed = 1, uploaded_bytes = ?, reused_bytes = ? WHERE version_id = ?",
                (total_uploaded_bytes, total_reused_bytes, version_id)
            )
            conn.execute(
                "UPDATE upload_sessions SET status = 'committed' WHERE upload_id = ?",
                (upload_id,)
            )

            updated_v = conn.execute("SELECT * FROM versions WHERE version_id = ?", (version_id,)).fetchone()
            return UploadCommitResponse(
                version_id=version_id,
                status="completed",
                total_logical_bytes=updated_v["total_logical_bytes"],
                uploaded_bytes=updated_v["uploaded_bytes"],
                reused_bytes=updated_v["reused_bytes"],
                created_at=updated_v["created_at"]
            )

    def list_versions(self) -> List[VersionSummary]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT version_id, created_at, total_logical_bytes, uploaded_bytes, reused_bytes, is_completed, source_label FROM versions WHERE is_completed = 1 ORDER BY created_at ASC"
            ).fetchall()
            return [
                VersionSummary(
                    version_id=r["version_id"],
                    created_at=r["created_at"],
                    total_logical_bytes=r["total_logical_bytes"],
                    uploaded_bytes=r["uploaded_bytes"],
                    reused_bytes=r["reused_bytes"],
                    is_completed=bool(r["is_completed"]),
                    source_label=r["source_label"]
                )
                for r in rows
            ]

    def get_version_manifest(self, version_id: str) -> Manifest:
        with self.db.transaction() as conn:
            v = conn.execute("SELECT * FROM versions WHERE version_id = ? AND is_completed = 1", (version_id,)).fetchone()
            if not v:
                raise NotFoundError(f"Version {version_id} not found or incomplete")

            file_rows = conn.execute(
                "SELECT path, type, size_bytes, mtime FROM version_files WHERE version_id = ? ORDER BY path ASC",
                (version_id,)
            ).fetchall()

            entries = []
            for fr in file_rows:
                p = fr["path"]
                t = ItemType(fr["type"])
                sz = fr["size_bytes"]
                mt = fr["mtime"]
                chunk_ids = []
                if t == ItemType.FILE:
                    c_rows = conn.execute(
                        "SELECT chunk_id FROM file_chunks WHERE version_id = ? AND path = ? ORDER BY chunk_order ASC",
                        (version_id, p)
                    ).fetchall()
                    chunk_ids = [cr["chunk_id"] for cr in c_rows]
                entries.append(ManifestEntry(path=p, type=t, size_bytes=sz, mtime=mt, chunk_ids=chunk_ids))

            return Manifest(entries=entries)

    def get_chunk_bytes(self, chunk_id: str) -> bytes:
        return self.cas.read_chunk(chunk_id)

    def verify_all_data(self) -> VerifyResponse:
        with self.db.transaction() as conn:
            rows = conn.execute("""
                SELECT DISTINCT fc.chunk_id 
                FROM file_chunks fc
                JOIN versions v ON fc.version_id = v.version_id
                WHERE v.is_completed = 1
            """).fetchall()
            
            all_chunks = [r["chunk_id"] for r in rows]
            corrupted_list: List[DamagedChunkInfo] = []

            for cid in all_chunks:
                is_valid = self.cas.verify_chunk(cid)
                if not is_valid:
                    status = "MISSING" if not self.cas.has_chunk(cid) else "CORRUPTED_HASH_MISMATCH"
                    impact_rows = conn.execute("""
                        SELECT fc.version_id, fc.path
                        FROM file_chunks fc
                        JOIN versions v ON fc.version_id = v.version_id
                        WHERE fc.chunk_id = ? AND v.is_completed = 1
                        ORDER BY fc.version_id, fc.path
                    """, (cid,)).fetchall()

                    affected_versions = sorted(list(set(ir["version_id"] for ir in impact_rows)))
                    affected_files = [DamagedFileInfo(version_id=ir["version_id"], path=ir["path"]) for ir in impact_rows]

                    corrupted_list.append(
                        DamagedChunkInfo(
                            chunk_id=cid,
                            status=status,
                            affected_versions=affected_versions,
                            affected_files=affected_files
                        )
                    )

            return VerifyResponse(
                total_chunks_checked=len(all_chunks),
                corrupted_chunks_count=len(corrupted_list),
                corrupted_chunks=corrupted_list
            )
