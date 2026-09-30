# BrokenVault - BitnBuild

## Team

- Member 1: Lead Systems Architect
- Member 2: Backend Core Developer
- Member 3: Client CLI Engineer
- Member 4: Quality & Test Engineer

## Supported setup

- Operating system or Docker version: Windows 10/11, macOS, Linux, or Docker 24.0+
- Programming language and version: Python 3.10+
- Required tools: `python`, `pip`

## Install

Open your terminal or command prompt (cmd/PowerShell) inside the `BitnBuild` directory:

```bash
# Navigate to the BitnBuild folder
cd d:\Hackathon\Participants_guide\BitnBuild

# Install dependencies and the package in editable mode
pip install -e .
```

## Start the complete system

Open a **dedicated terminal window** in the `BitnBuild` folder and start the BrokenVault server:

```bash
python -m brokenvault.server.app --host 127.0.0.1 --port 8000 --vault-dir ./vault_data
```

Once started, the server is live and provides:
- **Interactive Web Dashboard**: `http://127.0.0.1:8000/` — full-featured UI covering all 6 features
- **Swagger API Documentation & Testing UI**: `http://127.0.0.1:8000/docs`
- **JSON Version List Endpoint**: `http://127.0.0.1:8000/api/v1/versions`
- **Integrity Verification Endpoint**: `http://127.0.0.1:8000/api/v1/verify`

Leave this server terminal running.

---

## Commands

Open a **second terminal window** in the `BitnBuild` directory to run client commands.

### Back up a folder

Back up a source folder to the server:

```bash
# Example backing up a folder:
python -m brokenvault.client.cli backup ./sample_v1 --server http://127.0.0.1:8000
```

Output displays a summary table with:
- **Version ID**: Unique identifier (e.g., `v_f4b46ed7e2b3`)
- **Total Logical Bytes**: Total size of all files in the folder
- **Uploaded Chunk Bytes**: Original bytes of newly accepted chunks
- **Reused Chunk Bytes**: Bytes of chunks already stored and deduplicated

### List completed versions

Display all finalized backup versions stored in the vault:

```bash
python -m brokenvault.client.cli list --server http://127.0.0.1:8000
```

### Restore a version

Recreate a backup version byte-for-byte into an empty destination directory:

```bash
# Replace <VERSION_ID> with the version ID from backup or list (e.g., v_f4b46ed7e2b3)
python -m brokenvault.client.cli restore <VERSION_ID> ./restored_v1 --server http://127.0.0.1:8000
```

This reconstructs the exact directory structure, empty files, file contents, and original modification timestamps (`mtime`).

### Verify stored data

Perform a full cryptographic audit on all stored chunks used by completed versions:

```bash
python -m brokenvault.client.cli verify --server http://127.0.0.1:8000
```

- If all data is intact: Displays `[Integrity Verified]: All X stored chunks are healthy.`
- If any chunk is corrupted or missing: Displays an alert and an impact table listing the corrupted chunk ID, status (`CORRUPTED_HASH_MISMATCH` or `MISSING`), and all affected version IDs and relative file paths.

---

## Run tests

Run the entire automated test suite (9 test cases covering deduplication, exact restore, resumability, safe completion, dataset v1/v2, and damage detection):

```bash
pytest tests/ -v
```

---

## Web Dashboard (Frontend) — Fully Independent Execution

The frontend is a single-page web dashboard located in `frontend/`. It is automatically served by the BrokenVault server at `http://127.0.0.1:8000/` on port 8000.

> **Zero Dependency Between Frontend & CLI**: You can run the entire workflow completely from the **Web UI** (1-click Backup, 1-click Restore, live Verify audit, interactive charts) **OR** completely from the **CLI**. Neither requires the other, and both operate directly on the same underlying Content-Addressable Storage (CAS) and SQLite database.

### Features covered by the dashboard

| # | Feature | Direct Frontend Action | CLI Equivalent |
|---|---------|------------------------|----------------|
| 1 | **Backup** | Enter folder path (or click preset) & click **Start Backup** — auto-redirects to Resumable tab | `python -m brokenvault.client.cli backup <FOLDER>` |
| 2 | **List versions** | Live interactive table with sorting & Manifest Explorer | `python -m brokenvault.client.cli list` |
| 3 | **Restore** | Select version, pick destination & click **Restore Version** | `python -m brokenvault.client.cli restore <ID> <DEST>` |
| 4 | **Verify** | Click **Run Audit** to audit SHA-256 with full blast-radius report | `python -m brokenvault.client.cli verify` |
| 5 | **Dedup stats** | Real-time aggregate metrics & per-version comparison bar charts | Computed from version manifests |
| 6 | **Resumable uploads** | Auto-navigated here on backup start; live SSE chunk-by-chunk progress feed, animated progress bar, NEW/REUSED indicators; resume interrupted sessions by pasting an upload ID | `python -m brokenvault.client.cli backup --upload-id <ID>` |

### Frontend files

```
frontend/
├── index.html   # SPA shell: Dashboard, Backup, Versions, Restore, Verify, Dedup Stats, Resumable tabs
├── style.css    # Premium glassmorphic dark-mode design system + progress/chunk feed styles
└── app.js       # All API calls, SSE stream reader, direct action runners, and UI logic
```

Assets are served at `/assets/*` by FastAPI's `StaticFiles` mount.

> **Resumable tab detail**: When **Start Backup** is clicked the browser immediately switches to the **Resumable** tab and opens a streaming fetch to `POST /api/v1/actions/backup/stream`. The server emits Server-Sent Events — one `started` event with totals, one `chunk` event per chunk (colour-coded **NEW** or **REUSED**), and a final `done` event — giving real-time visibility into the upload and deduplication process. To resume an interrupted session, paste the `upload_id` shown in the completion summary into the Resume field and re-run.

---


Follow these exact steps to demonstrate all 6 requirements of the challenge.  
You can use the **Web Dashboard** (`http://127.0.0.1:8000/`) **or** the **CLI** — both are fully independent.

---

### Step 1 — Prepare Sample Datasets

> **Test Datasets**: Sample test datasets (`brokenvault_sample_v1.zip` and `brokenvault_sample_v2.zip`) are available for download under the [GitHub Releases](https://github.com/NoahReddyG/BrokenVault/releases/tag/version1) tab of this repository. You can use these to test and verify all features of the project.

Extract the sample datasets into your project root:

```powershell
# In PowerShell:
Expand-Archive -Path "..\brokenvault_sample_v1.zip" -DestinationPath ".\sample_v1" -Force
Expand-Archive -Path "..\brokenvault_sample_v2.zip" -DestinationPath ".\sample_v2" -Force
```

---

### Step 2 — Back up Version 1 (Feature 1 + Feature 6)

**Web Dashboard:**
1. Click **Backup** in the sidebar.
2. Enter `./sample_v1` in the *Source Folder Path* field (or click the `Preset: ./sample_v1` chip).
3. Click **Start Backup** — the browser automatically switches to the **Resumable** tab.
4. Watch the live progress feed: each chunk appears as **NEW** (purple) or **REUSED** (green).
5. When complete, note the **Version ID** and **Upload ID** shown in the summary card.

**CLI:**
```bash
python -m brokenvault.client.cli backup ./sample_v1 --server http://127.0.0.1:8000
```
*Observe: `Uploaded Chunk Bytes` equals total chunked bytes; `Reused Chunk Bytes` is 0 (first backup).*

---

### Step 3 — Back up Version 2 and Verify Deduplication (Feature 1 + Feature 5)

**Web Dashboard:**
1. Click **Backup** → enter `./sample_v2` → click **Start Backup**.
2. On the **Resumable** tab: watch **REUSED** (green) chunks fire for data shared with Version 1.
3. After completion, click **Dedup Stats** — the per-version bars show how much data was deduplicated.

**CLI:**
```bash
python -m brokenvault.client.cli backup ./sample_v2 --server http://127.0.0.1:8000
```
*Observe: `Uploaded Chunk Bytes` is significantly lower than `Total Logical Bytes`; `Reused Chunk Bytes` shows shared data.*

---

### Step 4 — List Completed Versions (Feature 2)

**Web Dashboard:**
1. Click **Versions** in the sidebar — both versions appear in the interactive table.
2. Click **Manifest** on any row to open the Manifest Explorer and browse every file and chunk.

**CLI:**
```bash
python -m brokenvault.client.cli list --server http://127.0.0.1:8000
```
*Both versions appear with Version ID, label, logical size, uploaded bytes, and reused bytes.*

---

### Step 5 — Restore Both Versions and Verify Exact Match (Feature 3)

**Web Dashboard:**
1. Click **Restore** in the sidebar.
2. Click **Pick →** to load the version list, then click a version row to auto-fill the Version ID.
3. Set destination to `./restored_v1` → click **Restore Version**.
4. Repeat for Version 2 with destination `./restored_v2`.

**CLI:**
```bash
python -m brokenvault.client.cli restore <V1_VERSION_ID> ./restored_v1 --server http://127.0.0.1:8000
python -m brokenvault.client.cli restore <V2_VERSION_ID> ./restored_v2 --server http://127.0.0.1:8000
```

Verify restored files match originals byte-for-byte:
```powershell
Get-ChildItem -Recurse ./restored_v1 | Measure-Object
Get-ChildItem -Recurse ./sample_v1   | Measure-Object
```

---

### Step 6 — Verify Healthy Storage (Feature 4)

**Web Dashboard:**
1. Click **Verify** in the sidebar → click **Run Audit**.
2. Result shows: *All chunks are healthy* with total chunk count.

**CLI:**
```bash
python -m brokenvault.client.cli verify --server http://127.0.0.1:8000
```
*Confirm all chunks pass the cryptographic SHA-256 hash check.*

---

### Step 7 — Simulate Damage and Audit Blast Radius (Feature 4)

Corrupt one stored chunk in the vault:

```powershell
$chunk = (Get-ChildItem -Path ./vault_data/chunks -File -Recurse | Select-Object -First 1).FullName
Set-Content -Path $chunk -Value "CORRUPTED_BYTES_FOR_TEST"
```

**Web Dashboard:** Click **Verify** → **Run Audit** — the report names the damaged chunk ID, its status (`CORRUPTED_HASH_MISMATCH`), and every affected version and file path.

**CLI:**
```bash
python -m brokenvault.client.cli verify --server http://127.0.0.1:8000
```
*The system pinpoints the damaged chunk and lists every affected version and file path.*

---

### Step 8 — Resume an Interrupted Backup (Feature 6)

**Web Dashboard:**
1. Start a backup normally (Step 2 flow) — note the **Upload ID** shown in the Resumable tab.
2. If interrupted (network drop, crash), click **Resumable** in the sidebar.
3. Paste the Upload ID into *Resume Upload ID* and the source path into *Source folder path* → click **Resume**.
4. Only missing chunks are re-uploaded; already-stored chunks are skipped automatically.

**CLI:**
```bash
python -m brokenvault.client.cli backup ./sample_v1 --upload-id <UPLOAD_ID> --server http://127.0.0.1:8000
```
*Already-stored chunks are skipped; only missing chunks are transferred.*

---


## Known limits

- Single backup operation active at a time.
- Symbolic links, POSIX ACLs, and extended filesystem attributes are excluded.

## External and AI-assisted work

- Libraries and services used: FastAPI, Uvicorn, HTTPX, Pydantic, Typer, Rich, SQLite3, Pytest.
- AI tools used and what they helped with: Antigravity AI assistant for building the interactive web UI accessible via localhost, refining architecture.md and README.md.
