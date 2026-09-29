# BrokenVault - BitnBuild

## Team

- Member 1: Lead Systems Architect
- Member 2: Backend Core Developer
- Member 3: Client CLI Engineer
- Member 4: Quality & Test Engineer

## Supported setup

- Operating system or Docker version: Windows 10/11, macOS, Linux, or Docker 24.0+
- Programming language and version: Python 3.10+
- Required tools: `python`, `pip`, `git`

## Install

Clone the repository and open your terminal inside the project directory:

```bash
# Clone the repository
git clone https://github.com/NoahReddyG/BrokenVault.git
cd BrokenVault

# Install dependencies and the package in editable mode
pip install -e .
```

## Start the complete system

Open a **dedicated terminal window** in the project directory and start the BrokenVault server:

```bash
python -m brokenvault.server.app --host 127.0.0.1 --port 8000 --vault-dir ./vault_data
```

Once started, the server is live and provides:
- **Interactive Web Dashboard**: `http://127.0.0.1:8000/`
- **Swagger API Documentation & Testing UI**: `http://127.0.0.1:8000/docs`
- **JSON Version List Endpoint**: `http://127.0.0.1:8000/api/v1/versions`
- **Integrity Verification Endpoint**: `http://127.0.0.1:8000/api/v1/verify`

Leave this server terminal running.

---

## Commands

Open a **second terminal window** in the project directory to run client commands.

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

## Demo steps

Follow these exact steps to demonstrate all requirements of the challenge:

### Step 1: Prepare Sample Datasets
Extract the provided sample datasets into separate folders:

```powershell
# In PowerShell:
Expand-Archive -Path "sample_data/brokenvault_sample_v1.zip" -DestinationPath ".\sample_v1" -Force
Expand-Archive -Path "sample_data/brokenvault_sample_v2.zip" -DestinationPath ".\sample_v2" -Force
```

### Step 2: Back up Version 1
```bash
python -m brokenvault.client.cli backup ./sample_v1
```
*Note the generated Version ID and observe that `Uploaded Chunk Bytes` equals total chunked bytes and `Reused Chunk Bytes` is 0.*

### Step 3: Back up Version 2 and Verify Deduplication
```bash
python -m brokenvault.client.cli backup ./sample_v2
```
*Observe that `Uploaded Chunk Bytes` is significantly lower than `Total Logical Bytes`, and `Reused Chunk Bytes` shows the data shared with Version 1.*

### Step 4: List Completed Versions
```bash
python -m brokenvault.client.cli list
```
*Both versions appear in the table with their respective metrics.*

### Step 5: Restore Both Versions and Verify Exact Match
```bash
python -m brokenvault.client.cli restore <V1_VERSION_ID> ./restored_v1
python -m brokenvault.client.cli restore <V2_VERSION_ID> ./restored_v2
```

Verify that restored files match the originals byte-for-byte:
```powershell
# Compare item count and verify contents match
Get-ChildItem -Recurse ./restored_v1 | Measure-Object
Get-ChildItem -Recurse ./sample_v1 | Measure-Object
```

### Step 6: Verify Healthy Storage
```bash
python -m brokenvault.client.cli verify
```
*Confirm all chunks pass the cryptographic SHA-256 hash check.*

### Step 7: Simulate Damage and Audit Blast Radius
Modify or corrupt one stored chunk in the vault:

```powershell
# Pick the first chunk in vault_data/chunks and tamper its content:
$chunk = (Get-ChildItem -Path ./vault_data/chunks -File -Recurse | Select-Object -First 1).FullName
Set-Content -Path $chunk -Value "CORRUPTED_BYTES_FOR_TEST"
```

Run verification again:
```bash
python -m brokenvault.client.cli verify
```
*Confirm the system pinpoints the damaged chunk ID and lists every affected version and file path.*

---

## Known limits

- Single backup operation active at a time.
- Symbolic links, POSIX ACLs, and extended filesystem attributes are excluded.

## External and AI-assisted work

- Libraries and services used: FastAPI, Uvicorn, HTTPX, Pydantic, Typer, Rich, SQLite3, Pytest.
- AI tools used and what they helped with: Antigravity AI assistant for building the interactive web UI accessible via localhost, refining architecture.md and README.md.
