/* ===========================
   BrokenVault Dashboard — app.js
   Communicates with backend API at /api/v1/*
   All 6 features:
     1. Backup
     2. List versions
     3. Restore
     4. Verify (integrity audit)
     5. Dedup stats
     6. Resumable upload (resume via upload_id field)
=========================== */

const API = '';  // same origin — FastAPI serves both

// ─── Utility helpers ───────────────────────────────────────────────

function fmt(bytes) {
  if (bytes == null || isNaN(bytes)) return '—';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + units[i];
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function dedupPct(uploaded, reused) {
  const total = (uploaded || 0) + (reused || 0);
  if (!total) return '0%';
  return ((reused / total) * 100).toFixed(1) + '%';
}

function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ';
  t.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function showResult(id, html, type = 'info') {
  const el = document.getElementById(id);
  el.innerHTML = html;
  el.className = `result-panel ${type}`;
  el.classList.remove('hidden');
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ─── Tab navigation ────────────────────────────────────────────────

const TAB_META = {
  dashboard:  { title: 'Dashboard',               subtitle: 'Real-time vault overview' },
  backup:     { title: 'Backup',                   subtitle: 'Create a new version from a local folder' },
  versions:   { title: 'Versions',                 subtitle: 'Browse all completed backup versions' },
  restore:    { title: 'Restore',                  subtitle: 'Reconstruct any version byte-for-byte' },
  verify:     { title: 'Verify',                   subtitle: 'Cryptographic SHA-256 integrity audit' },
  dedup:      { title: 'Dedup Stats',              subtitle: 'Visualise deduplication savings' },
  resumable:  { title: 'Resumable Backup',         subtitle: 'Live chunk-by-chunk upload progress' },
};

function switchTab(name) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`nav-${name}`)?.classList.add('active');
  document.getElementById(`tab-${name}`)?.classList.add('active');
  const meta = TAB_META[name] || {};
  document.getElementById('page-title').textContent = meta.title || name;
  document.getElementById('page-subtitle').textContent = meta.subtitle || '';
  if (name === 'versions' || name === 'dashboard') loadVersions();
  if (name === 'dedup') loadDedupStats();
  if (name === 'restore') loadRestoreVersionList();
}

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});
document.getElementById('refresh-btn').addEventListener('click', () => {
  const active = document.querySelector('.tab-panel.active')?.id?.replace('tab-', '');
  if (active) switchTab(active);
  checkServerHealth();
});

// ─── Server health ──────────────────────────────────────────────────

async function checkServerHealth() {
  const dot = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  try {
    await apiFetch('/api/v1/versions');
    dot.className = 'status-dot online';
    label.textContent = 'Server online';
  } catch {
    dot.className = 'status-dot offline';
    label.textContent = 'Server offline';
  }
}

// ─── Feature 2: List Versions ───────────────────────────────────────

let _versions = [];

async function loadVersions() {
  try {
    const data = await apiFetch('/api/v1/versions');
    _versions = data.versions || [];
    renderVersionsTable();
    renderDashboard();
    renderVersionChart();
  } catch (e) {
    toast('Failed to load versions: ' + e.message, 'error');
  }
}

function renderVersionsTable() {
  const el = document.getElementById('versions-table');
  if (!_versions.length) {
    el.innerHTML = '<div class="empty-state">No completed versions found.</div>';
    return;
  }
  const rows = _versions.map(v => `
    <tr class="version-row" data-id="${v.version_id}" style="cursor:pointer">
      <td><span class="mono">${v.version_id}</span></td>
      <td>${v.source_label || '<em style="color:var(--text-muted)">—</em>'}</td>
      <td>${fmtDate(v.created_at)}</td>
      <td class="mono">${fmt(v.total_logical_bytes)}</td>
      <td class="mono" style="color:var(--accent)">${fmt(v.uploaded_bytes)}</td>
      <td class="mono" style="color:var(--green)">${fmt(v.reused_bytes)}</td>
      <td>${dedupPct(v.uploaded_bytes, v.reused_bytes)} <span class="badge-green">saved</span></td>
      <td style="white-space:nowrap">
        <button class="btn btn-ghost btn-sm inspect-btn" data-id="${v.version_id}">Manifest</button>
        <button class="btn btn-secondary btn-sm table-restore-btn" data-id="${v.version_id}" style="margin-left:6px;padding:3px 8px;font-size:0.75rem">Restore</button>
      </td>
    </tr>`).join('');

  el.innerHTML = `
    <table>
      <thead><tr>
        <th>Version ID</th><th>Label</th><th>Created</th>
        <th>Logical</th><th>Uploaded</th><th>Reused</th>
        <th>Dedup</th><th>Actions</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  el.querySelectorAll('.inspect-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      loadManifest(btn.dataset.id);
    });
  });

  el.querySelectorAll('.table-restore-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const vId = btn.dataset.id;
      switchTab('restore');
      document.getElementById('restore-version-id').value = vId;
      document.getElementById('restore-dest').value = `./restored_${vId}`;
      toast(`Ready to restore version: ${vId}`, 'info');
    });
  });
}

// ─── Manifest viewer ─────────────────────────────────────────────────

async function loadManifest(versionId) {
  const viewer = document.getElementById('manifest-viewer');
  viewer.innerHTML = '<div class="empty-state">Loading manifest…</div>';
  try {
    const data = await apiFetch(`/api/v1/versions/${versionId}/manifest`);
    const entries = data.entries || [];
    if (!entries.length) {
      viewer.innerHTML = '<div class="empty-state">No entries in manifest.</div>';
      return;
    }
    viewer.innerHTML = entries.map(e => {
      const isDir = e.type === 'directory';
      const icon = isDir
        ? `<svg class="manifest-type-icon" viewBox="0 0 16 16" fill="none"><path d="M2 4.5A1.5 1.5 0 013.5 3h3l1.5 2H13a1.5 1.5 0 011.5 1.5v6A1.5 1.5 0 0113 14H3a1.5 1.5 0 01-1.5-1.5v-8z" stroke="var(--amber)" stroke-width="1.2"/></svg>`
        : `<svg class="manifest-type-icon" viewBox="0 0 16 16" fill="none"><path d="M3 2h7l4 4v9a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="var(--accent)" stroke-width="1.2"/><path d="M10 2v4h4" stroke="var(--accent)" stroke-width="1.2"/></svg>`;
      return `<div class="manifest-entry">${icon}<span class="manifest-path">${e.path}</span><span class="manifest-size">${fmt(e.size_bytes)}${e.chunk_ids?.length ? ' · ' + e.chunk_ids.length + ' chunk(s)' : ''}</span></div>`;
    }).join('');
    toast(`Manifest loaded for ${versionId}`, 'success');
  } catch (err) {
    viewer.innerHTML = `<div class="empty-state" style="color:var(--red)">Error: ${err.message}</div>`;
    toast('Failed to load manifest: ' + err.message, 'error');
  }
}

// ─── Dashboard rendering ──────────────────────────────────────────────

function renderDashboard() {
  const versions = _versions;
  const totalLogical = versions.reduce((s, v) => s + (v.total_logical_bytes || 0), 0);
  const totalUploaded = versions.reduce((s, v) => s + (v.uploaded_bytes || 0), 0);
  const totalReused  = versions.reduce((s, v) => s + (v.reused_bytes  || 0), 0);
  const totalSaved   = totalReused;
  const ratio = (totalUploaded + totalReused) ? ((totalReused / (totalUploaded + totalReused)) * 100).toFixed(1) + '%' : '0%';

  document.getElementById('total-versions').textContent = versions.length;
  document.getElementById('total-logical').textContent  = fmt(totalLogical);
  document.getElementById('total-saved').textContent    = fmt(totalSaved);
  document.getElementById('dedup-ratio').textContent    = ratio;

  // recent versions
  const recent = [...versions].reverse().slice(0, 5);
  const recentEl = document.getElementById('recent-versions-table');
  if (!recent.length) {
    recentEl.innerHTML = '<div class="empty-state">No versions yet.</div>';
    return;
  }
  recentEl.innerHTML = `
    <table>
      <thead><tr><th>Version ID</th><th>Label</th><th>Created</th><th>Total</th><th>Saved</th></tr></thead>
      <tbody>
        ${recent.map(v => `
          <tr>
            <td><span class="mono">${v.version_id}</span></td>
            <td>${v.source_label || '—'}</td>
            <td>${fmtDate(v.created_at)}</td>
            <td class="mono">${fmt(v.total_logical_bytes)}</td>
            <td class="mono" style="color:var(--green)">${fmt(v.reused_bytes)}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}

// ─── Feature 5: Version storage chart ─────────────────────────────────

function renderVersionChart() {
  const el = document.getElementById('version-chart');
  if (!_versions.length) {
    el.innerHTML = '<div class="empty-state">No backup versions found.</div>';
    return;
  }
  const max = Math.max(..._versions.map(v => (v.uploaded_bytes || 0) + (v.reused_bytes || 0)), 1);
  const bars = _versions.map(v => {
    const up = v.uploaded_bytes || 0;
    const re = v.reused_bytes  || 0;
    const upW = ((up / max) * 100).toFixed(1);
    const reW = ((re / max) * 100).toFixed(1);
    const label = (v.source_label || v.version_id).slice(0, 16);
    return `
      <div class="chart-row">
        <span class="chart-label" title="${v.source_label || v.version_id}">${label}</span>
        <div class="chart-bars">
          <div class="chart-bar-wrap">
            <div class="chart-bar bar-upload" style="width:${upW}%"></div>
            <span class="chart-value">${fmt(up)}</span>
          </div>
          <div class="chart-bar-wrap">
            <div class="chart-bar bar-reuse" style="width:${reW}%"></div>
            <span class="chart-value">${fmt(re)}</span>
          </div>
        </div>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="chart-legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--accent)"></div>Uploaded (new)</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--green)"></div>Reused (dedup)</div>
    </div>
    <div class="chart-container">${bars}</div>`;
}

// ─── Feature 1 + 6: Backup → Resumable SSE streaming ─────────────────

/**
 * Reset the Resumable tab to a blank "waiting" state before a new run.
 */
function resetResumableUI() {
  document.getElementById('resumable-status-title').textContent = 'Connecting…';
  const badge = document.getElementById('resumable-upload-id-badge');
  badge.style.display = 'none';
  badge.textContent = '';
  document.getElementById('resumable-progress-wrap').style.display = 'none';
  document.getElementById('resumable-progress-bar').style.width = '0%';
  document.getElementById('resumable-progress-bar').classList.remove('done');
  document.getElementById('resumable-pct-label').textContent = '0%';
  document.getElementById('resumable-bytes-label').textContent = '0 B / 0 B';
  document.getElementById('rc-files').textContent = '0 files';
  document.getElementById('rc-new').textContent   = '0 new chunks';
  document.getElementById('rc-reused').textContent= '0 reused';
  document.getElementById('rc-total').textContent = '0 total';
  document.getElementById('resumable-feed').innerHTML =
    '<div class="empty-state" id="resumable-feed-empty">Connecting to vault…</div>';
  document.getElementById('resumable-done-card').classList.add('hidden');
}

/**
 * Add one row to the chunk feed (max 200 rows — auto-prune oldest).
 */
function appendChunkRow(file, chunkId, status) {
  const feed = document.getElementById('resumable-feed');
  // Remove placeholder on first real event
  const empty = feed.querySelector('.empty-state');
  if (empty) empty.remove();

  const row = document.createElement('div');
  row.className = `chunk-row ${status}`;
  row.innerHTML =
    `<span class="chunk-status-pill ${status === 'uploaded' ? 'pill-new' : 'pill-reused'}">
       ${status === 'uploaded' ? 'NEW' : 'REUSED'}
     </span>` +
    `<span class="chunk-file" title="${file}">${file || '—'}</span>` +
    `<span class="chunk-id">${chunkId}</span>`;
  feed.prepend(row);

  // Keep feed tidy — prune beyond 200 rows
  const rows = feed.querySelectorAll('.chunk-row');
  if (rows.length > 200) rows[rows.length - 1].remove();

  // Auto-scroll to top (newest)
  feed.scrollTop = 0;
}

/**
 * Run a streaming backup and update the Resumable tab in real-time.
 * @param {string} sourcePath
 * @param {string} label
 * @param {string|null} uploadId
 */
function runStreamingBackup(sourcePath, label, uploadId) {
  resetResumableUI();
  switchTab('resumable');

  const payload = JSON.stringify({
    source_dir:   sourcePath,
    source_label: label || undefined,
    upload_id:    uploadId || undefined,
  });

  // We use fetch + ReadableStream instead of EventSource so we can POST
  fetch('/api/v1/actions/backup/stream', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    payload,
  }).then(response => {
    if (!response.ok) {
      return response.json().then(err => { throw new Error(err.detail || response.statusText); });
    }

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    function processBuffer() {
      // SSE frames are separated by blank lines (\n\n)
      const frames = buffer.split('\n\n');
      buffer = frames.pop(); // keep incomplete frame
      for (const frame of frames) {
        if (!frame.trim()) continue;
        let eventType = 'message';
        let dataLine  = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim();
          if (line.startsWith('data: '))  dataLine  = line.slice(6).trim();
        }
        if (!dataLine) continue;
        try {
          handleSSEEvent(eventType, JSON.parse(dataLine));
        } catch { /* ignore malformed */ }
      }
    }

    function pump() {
      return reader.read().then(({ done, value }) => {
        if (done) return;
        buffer += decoder.decode(value, { stream: true });
        processBuffer();
        return pump();
      });
    }

    return pump();
  }).catch(err => {
    document.getElementById('resumable-status-title').textContent = '✗ Backup failed';
    document.getElementById('resumable-feed').innerHTML =
      `<div class="empty-state" style="color:var(--red)">Error: ${err.message}</div>`;
    toast('Backup failed: ' + err.message, 'error');
  });
}

/**
 * Dispatch a single SSE event to update the Resumable UI.
 */
function handleSSEEvent(type, d) {
  switch (type) {

    case 'started': {
      const badge = document.getElementById('resumable-upload-id-badge');
      badge.textContent = d.upload_id;
      badge.style.display = 'inline';
      document.getElementById('resumable-status-title').textContent = '⚡ Backup in progress…';
      document.getElementById('resumable-progress-wrap').style.display = 'block';
      document.getElementById('rc-files').textContent   = `${d.total_files} files`;
      document.getElementById('rc-new').textContent     = `${d.new_chunks} new chunks`;
      document.getElementById('rc-reused').textContent  = `${d.reused_chunks} reused`;
      document.getElementById('rc-total').textContent   = `${d.total_chunks} total`;
      document.getElementById('resumable-bytes-label').textContent =
        `0 B / ${fmt(d.total_bytes)}`;
      break;
    }

    case 'chunk': {
      const pct = d.total_chunks
        ? Math.round((d.done_chunks / d.total_chunks) * 100)
        : 0;
      document.getElementById('resumable-progress-bar').style.width = pct + '%';
      document.getElementById('resumable-pct-label').textContent = pct + '%';
      document.getElementById('resumable-bytes-label').textContent =
        `${fmt(d.uploaded_bytes)} / ${fmt(d.total_bytes)}`;
      appendChunkRow(d.file, d.chunk_id, d.status);
      break;
    }

    case 'done': {
      // Progress bar to 100%
      const bar = document.getElementById('resumable-progress-bar');
      bar.style.width = '100%';
      bar.classList.add('done');
      document.getElementById('resumable-pct-label').textContent = '100%';
      document.getElementById('resumable-status-title').textContent = '✓ Backup Complete';

      const dedup = dedupPct(d.uploaded_bytes, d.reused_bytes);
      const doneCard = document.getElementById('resumable-done-card');
      document.getElementById('resumable-done-body').innerHTML =
        `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;padding:4px 0 8px">`+
        `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.72rem;color:var(--text-muted)">Version ID</span><br><strong class="mono" style="font-size:0.8rem;color:var(--accent)">${d.version_id}</strong></div>`+
        `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.72rem;color:var(--text-muted)">Upload ID</span><br><strong class="mono" style="font-size:0.8rem;color:var(--text-secondary)">${d.upload_id}</strong></div>`+
        `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.72rem;color:var(--text-muted)">Total Files</span><br><strong class="mono" style="font-size:0.8rem">${d.total_files}</strong></div>`+
        `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.72rem;color:var(--text-muted)">Logical Size</span><br><strong class="mono" style="font-size:0.8rem">${fmt(d.total_logical_bytes)}</strong></div>`+
        `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.72rem;color:var(--text-muted)">Uploaded (New)</span><br><strong class="mono" style="font-size:0.8rem;color:var(--amber)">${fmt(d.uploaded_bytes)}</strong></div>`+
        `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.72rem;color:var(--text-muted)">Reused (Dedup)</span><br><strong class="mono" style="font-size:0.8rem;color:var(--green)">${fmt(d.reused_bytes)} (${dedup})</strong></div>`+
        `</div>`;
      doneCard.classList.remove('hidden');
      toast(`Backup complete! Version: ${d.version_id}`, 'success');
      // Refresh versions + dashboard in background
      loadVersions();
      break;
    }

    case 'error': {
      document.getElementById('resumable-status-title').textContent = '✗ Backup Failed';
      document.getElementById('resumable-feed').insertAdjacentHTML('afterbegin',
        `<div class="chunk-row" style="border-left:3px solid var(--red);color:var(--red)">${d.message}</div>`);
      toast('Backup error: ' + d.message, 'error');
      break;
    }
  }
}

// Backup button — redirect to Resumable tab + start SSE stream
document.getElementById('backup-btn').addEventListener('click', () => {
  const folderPath = document.getElementById('backup-path').value.trim();
  const label      = document.getElementById('backup-label').value.trim();
  const uploadId   = document.getElementById('backup-upload-id').value.trim();

  if (!folderPath) { toast('Please enter a folder path.', 'error'); return; }

  runStreamingBackup(folderPath, label, uploadId || null);
});

// Resume button on the Resumable tab itself
document.getElementById('resume-btn').addEventListener('click', () => {
  const uploadId   = document.getElementById('resume-upload-id').value.trim();
  const sourcePath = document.getElementById('resume-source-path').value.trim();
  if (!sourcePath) { toast('Enter the source folder path to resume.', 'error'); return; }
  runStreamingBackup(sourcePath, '', uploadId || null);
});


document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById('backup-path').value = btn.dataset.path;
    document.getElementById('backup-label').value = btn.dataset.label;
    toast(`Loaded path: ${btn.dataset.path}`, 'info');
  });
});

// ─── Feature 3: Restore ───────────────────────────────────────────────

async function loadRestoreVersionList() {
  const el = document.getElementById('restore-version-list');
  try {
    const data = await apiFetch('/api/v1/versions');
    _versions = data.versions || [];
    if (!_versions.length) {
      el.innerHTML = '<div class="empty-state">No completed versions available.</div>';
      return;
    }
    el.innerHTML = _versions.map(v => `
      <div class="version-pick-row" data-id="${v.version_id}">
        <span class="version-pick-id">${v.version_id}</span>
        <span style="color:var(--text-secondary);font-size:0.8rem">${v.source_label || ''}</span>
        <span class="version-pick-date">${fmtDate(v.created_at)}</span>
        <span style="margin-left:auto;font-family:var(--mono);font-size:0.75rem;color:var(--text-muted)">${fmt(v.total_logical_bytes)}</span>
      </div>`).join('');

    el.querySelectorAll('.version-pick-row').forEach(row => {
      row.addEventListener('click', () => {
        const vId = row.dataset.id;
        document.getElementById('restore-version-id').value = vId;
        const destInput = document.getElementById('restore-dest');
        if (!destInput.value.trim()) {
          destInput.value = `./restored_${vId}`;
        }
        toast(`Selected version: ${vId}`, 'info');
      });
    });
  } catch (e) {
    el.innerHTML = `<div class="empty-state" style="color:var(--red)">Error: ${e.message}</div>`;
  }
}

document.getElementById('restore-pick-btn').addEventListener('click', () => {
  document.getElementById('restore-version-picker').scrollIntoView({ behavior: 'smooth' });
  loadRestoreVersionList();
});

document.getElementById('restore-btn').addEventListener('click', async () => {
  const vId  = document.getElementById('restore-version-id').value.trim();
  const dest = document.getElementById('restore-dest').value.trim();
  if (!vId || !dest) { toast('Enter both Version ID and destination.', 'error'); return; }

  const btn = document.getElementById('restore-btn');
  btn.disabled = true;
  btn.innerHTML = `<span class="pulse-ring" style="display:inline-block;width:12px;height:12px;border:2px solid currentColor;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px"></span> Restoring…`;

  showResult('restore-result',
    `<strong>⏳ Restoring version directly from vault…</strong><br>` +
    `<span style="font-size:0.85rem;color:var(--text-muted)">Fetching chunks from CAS, verifying SHA-256 integrity, reconstructing files and timestamps…</span>`,
    'info'
  );

  try {
    const res = await apiFetch('/api/v1/actions/restore', {
      method: 'POST',
      body: JSON.stringify({
        version_id: vId,
        destination_dir: dest,
      }),
    });

    showResult('restore-result',
      `<strong>✓ Version Restored Successfully!</strong><br><br>` +
      `<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));gap:8px;margin:8px 0 12px 0">` +
      `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.75rem;color:var(--text-muted)">Version</span><br><strong class="mono" style="font-size:0.82rem;color:var(--accent)">${res.version_id}</strong></div>` +
      `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.75rem;color:var(--text-muted)">Items Restored</span><br><strong class="mono" style="font-size:0.82rem;color:var(--green)">${res.entries_restored} entries</strong></div>` +
      `  <div style="background:rgba(0,0,0,0.25);padding:8px;border-radius:6px"><span style="font-size:0.75rem;color:var(--text-muted)">Data Reconstructed</span><br><strong class="mono" style="font-size:0.82rem">${fmt(res.total_bytes)}</strong></div>` +
      `</div>` +
      `<div style="font-size:0.8rem;background:rgba(0,0,0,0.2);padding:8px 12px;border-radius:6px;word-break:break-all">` +
      `  <strong>Restored to:</strong> <code class="mono">${res.destination_dir}</code>` +
      `</div>` +
      `<span style="font-size:0.78rem;color:var(--text-muted);display:block;margin-top:8px">All modification timestamps and directory structures have been faithfully reconstructed.</span>`,
      'success'
    );
    toast(`Version ${vId} restored to ${dest}`, 'success');
  } catch (e) {
    showResult('restore-result',
      `<strong>✗ Restore Failed</strong><br>` +
      `<span style="font-size:0.85rem">${e.message}</span>`,
      'error'
    );
    toast('Restore failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M10 7V16m0-9l3 3M10 7l-3 3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg> Restore Version`;
  }
});

// ─── Feature 4: Verify ────────────────────────────────────────────────

document.getElementById('verify-btn').addEventListener('click', async () => {
  const btn = document.getElementById('verify-btn');
  const report = document.getElementById('verify-report');
  btn.disabled = true;
  btn.textContent = 'Auditing…';
  report.innerHTML = '<div class="empty-state">Running SHA-256 integrity audit…</div>';

  try {
    const data = await apiFetch('/api/v1/verify');
    renderVerifyReport(data);
    const ok = data.corrupted_chunks_count === 0;
    toast(ok ? `All ${data.total_chunks_checked} chunks verified ✓` : `${data.corrupted_chunks_count} corrupted chunk(s) found!`, ok ? 'success' : 'error');
  } catch (e) {
    report.innerHTML = `<div class="empty-state" style="color:var(--red)">Audit failed: ${e.message}</div>`;
    toast('Audit error: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M10 2l1.5 4.5H16l-3.5 2.5 1.5 4.5L10 11l-4 2.5 1.5-4.5L4 6.5h4.5L10 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg> Run Audit`;
  }
});

function renderVerifyReport(data) {
  const el = document.getElementById('verify-report');
  const ok = data.corrupted_chunks_count === 0;
  let html = `
    <div class="${ok ? 'verify-pass' : 'verify-pass verify-fail'}">
      <span style="font-size:1.2rem">${ok ? '✓' : '✗'}</span>
      <div>
        <div>${ok ? 'All chunks are healthy' : `${data.corrupted_chunks_count} corrupted chunk(s) detected`}</div>
        <div style="font-size:0.78rem;opacity:0.75;margin-top:2px">Total chunks audited: ${data.total_chunks_checked}</div>
      </div>
    </div>`;

  if (!ok && data.corrupted_chunks?.length) {
    html += data.corrupted_chunks.map(c => `
      <div class="chunk-card">
        <div class="chunk-card-header">
          <span class="badge-red">${c.status}</span>
          <span class="chunk-id">${c.chunk_id}</span>
        </div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:6px">
          Affected versions: ${c.affected_versions?.join(', ') || '—'}
        </div>
        <div class="chunk-affected">
          <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:4px">Affected files:</div>
          <ul style="list-style:none;padding-left:8px">
            ${(c.affected_files || []).map(f =>
              `<li style="color:var(--text-muted);font-family:var(--mono);font-size:0.73rem;padding:2px 0">${f.version_id} → ${f.path}</li>`
            ).join('')}
          </ul>
        </div>
      </div>`).join('');
  }

  el.innerHTML = html;
}

// ─── Feature 5: Dedup Stats ───────────────────────────────────────────

async function loadDedupStats() {
  try {
    const data = await apiFetch('/api/v1/versions');
    const versions = data.versions || [];
    const totalLogical  = versions.reduce((s,v) => s + (v.total_logical_bytes||0), 0);
    const totalUploaded = versions.reduce((s,v) => s + (v.uploaded_bytes||0), 0);
    const totalReused   = versions.reduce((s,v) => s + (v.reused_bytes||0), 0);
    const ratio = (totalUploaded + totalReused) ? ((totalReused/(totalUploaded+totalReused))*100).toFixed(1)+'%' : '0%';

    document.getElementById('dd-total').textContent    = fmt(totalLogical);
    document.getElementById('dd-uploaded').textContent = fmt(totalUploaded);
    document.getElementById('dd-reused').textContent   = fmt(totalReused);
    document.getElementById('dd-ratio').textContent    = ratio;

    renderDedupDetail(versions);
  } catch (e) {
    toast('Failed to load dedup stats: ' + e.message, 'error');
  }
}

function renderDedupDetail(versions) {
  const el = document.getElementById('dedup-chart-detail');
  if (!versions.length) {
    el.innerHTML = '<div class="empty-state">No versions found.</div>';
    return;
  }
  const max = Math.max(...versions.map(v => (v.uploaded_bytes||0)+(v.reused_bytes||0)), 1);
  el.innerHTML = `
    <div class="chart-legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--accent)"></div>Uploaded (new data)</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--green)"></div>Reused (deduplicated)</div>
    </div>
    <div class="chart-container">
      ${versions.map(v => {
        const up = v.uploaded_bytes || 0;
        const re = v.reused_bytes   || 0;
        const total = up + re;
        const pct = total ? ((re/total)*100).toFixed(1)+'%' : '0%';
        const upW = ((up/max)*100).toFixed(1);
        const reW = ((re/max)*100).toFixed(1);
        const label = (v.source_label || v.version_id).slice(0,18);
        return `
          <div class="chart-row">
            <span class="chart-label" title="${v.version_id}\n${v.source_label||''}">${label}</span>
            <div class="chart-bars">
              <div class="chart-bar-wrap">
                <div class="chart-bar bar-upload" style="width:${upW}%"></div>
                <span class="chart-value">${fmt(up)} uploaded</span>
              </div>
              <div class="chart-bar-wrap">
                <div class="chart-bar bar-reuse" style="width:${reW}%"></div>
                <span class="chart-value">${fmt(re)} reused · <strong style="color:var(--green)">${pct} saved</strong></span>
              </div>
            </div>
          </div>`;
      }).join('')}
    </div>`;
}

document.getElementById('dedup-refresh-btn').addEventListener('click', loadDedupStats);
document.getElementById('versions-refresh-btn').addEventListener('click', loadVersions);

// ─── Init ────────────────────────────────────────────────────────────

checkServerHealth();
loadVersions();
switchTab('dashboard');

// Refresh server health every 30s
setInterval(checkServerHealth, 30000);
