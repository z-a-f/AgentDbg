const runListEl = document.getElementById('run-list');
const runListErrorEl = document.getElementById('run-list-error');
const btnRefreshEl = document.getElementById('btn-refresh');
const btnCopyLinkEl = document.getElementById('btn-copy-link');
const btnCopyRunIdEl = document.getElementById('btn-copy-run-id');
const runHeaderEl = document.getElementById('run-header');
const timelineToolbarEl = document.getElementById('timeline-toolbar');
const eventCountEl = document.getElementById('event-count');
const filterChipsEl = document.getElementById('filter-chips');
const timelineEmptyEl = document.getElementById('timeline-empty');
const timelineErrorEl = document.getElementById('timeline-error');
const timelineEventsEl = document.getElementById('timeline-events');

let currentEvents = [];
let currentFilter = 'all';
let lastRuns = [];
let currentRunId = null;
let fetchAbort = null;
const escapeDiv = document.createElement('div');

function getRunIdFromUrl() {
  const url = new URL(window.location.href);
  const q = url.searchParams.get('run_id');
  if (q) return q;
  const parts = url.pathname.split('/').filter(Boolean);
  if (parts.length === 0) return null;
  const last = parts[parts.length - 1];
  const looksLikeId = /^[0-9a-fA-F-]{8,}$/.test(last);
  return looksLikeId ? last : null;
}

function getRunUrl(runId) {
  if (!runId) return '';
  const url = new URL(window.location.href);
  url.pathname = '/';
  url.searchParams.set('run_id', runId);
  return url.toString();
}

function setUrlRunId(runId, { replace = false } = {}) {
  if (!runId) return;
  const url = new URL(window.location.href);
  url.pathname = '/';
  url.searchParams.set('run_id', runId);
  const method = replace ? 'replaceState' : 'pushState';
  window.history[method]({ run_id: runId }, '', url.toString());
}

(function canonicalizeOnBoot() {
  const url = new URL(window.location.href);
  const hasQuery = url.searchParams.has('run_id');
  const runIdFromPath = getRunIdFromUrl();
  if (!hasQuery && runIdFromPath) {
    setUrlRunId(runIdFromPath, { replace: true });
  }
})();

function updateCopyButtonsState() {
  const hasRun = !!currentRunId;
  if (btnCopyLinkEl) btnCopyLinkEl.disabled = !hasRun;
  if (btnCopyRunIdEl) btnCopyRunIdEl.disabled = !hasRun;
}

async function copyRunLink() {
  if (!currentRunId) return;
  const url = getRunUrl(currentRunId);
  try {
    await navigator.clipboard.writeText(url);
    if (btnCopyLinkEl) btnCopyLinkEl.textContent = 'Copied!';
    setTimeout(() => { if (btnCopyLinkEl) btnCopyLinkEl.textContent = 'Copy link'; }, 1500);
  } catch (_) {}
}

async function copyRunId() {
  if (!currentRunId) return;
  try {
    await navigator.clipboard.writeText(currentRunId);
    if (btnCopyRunIdEl) btnCopyRunIdEl.textContent = 'Copied!';
    setTimeout(() => { if (btnCopyRunIdEl) btnCopyRunIdEl.textContent = 'Copy run ID'; }, 1500);
  } catch (_) {}
}

function showRunListError(msg) {
  runListErrorEl.textContent = msg;
  runListErrorEl.style.display = 'block';
}
function hideRunListError() {
  runListErrorEl.style.display = 'none';
}
const runNotFoundBannerEl = document.getElementById('run-not-found-banner');
function showRunNotFoundBanner() {
  if (runNotFoundBannerEl) runNotFoundBannerEl.style.display = 'block';
}
function hideRunNotFoundBanner() {
  if (runNotFoundBannerEl) runNotFoundBannerEl.style.display = 'none';
}
function setRunListLoading(loading) {
  if (loading) {
    runListEl.innerHTML = '<div class="run-list-loading"><span class="spinner"></span><span>Loading…</span></div>';
    if (btnRefreshEl) btnRefreshEl.disabled = true;
  } else {
    if (btnRefreshEl) btnRefreshEl.disabled = false;
  }
}
function showTimelineError(msg) {
  timelineEmptyEl.style.display = 'none';
  timelineEventsEl.innerHTML = '';
  timelineErrorEl.textContent = msg;
  timelineErrorEl.style.display = 'block';
}
function hideTimelineError() {
  timelineErrorEl.style.display = 'none';
}

async function loadRuns() {
  hideRunListError();
  setRunListLoading(true);
  try {
    const r = await fetch('/api/runs');
    if (!r.ok) throw new Error(r.statusText || 'Failed to load runs');
    const data = await r.json();
    const runs = data.runs || [];
    lastRuns = runs;
    runListEl.innerHTML = '';
    if (runs.length === 0) {
      runListEl.innerHTML = '<div class="empty">No runs yet.</div>';
    } else {
      const frag = document.createDocumentFragment();
      runs.forEach((run) => {
        const div = document.createElement('div');
        div.className = 'run-item';
        div.dataset.runId = run.run_id;
        const name = run.run_name || run.run_id?.slice(0, 8) || '—';
        const meta = [run.started_at || '', run.status || '', run.duration_ms != null ? run.duration_ms + ' ms' : ''].filter(Boolean).join(' · ');
        div.innerHTML = '<span class="run-name">' + escapeHtml(name) + '</span><br><span class="run-meta">' + escapeHtml(meta) + '</span>';
        div.addEventListener('click', () => selectRun(run.run_id));
        frag.appendChild(div);
      });
      runListEl.appendChild(frag);
      const urlRunId = getRunIdFromUrl();
      let toSelect = runs[0].run_id;
      if (urlRunId) {
        const exact = runs.find((r) => r.run_id === urlRunId);
        const byPrefix = runs.find((r) => r.run_id && r.run_id.startsWith(urlRunId));
        if (exact) toSelect = exact.run_id;
        else if (byPrefix) toSelect = byPrefix.run_id;
        else {
          showRunNotFoundBanner();
          selectRun(runs[0].run_id, { fromFallback: true });
          return;
        }
      }
      selectRun(toSelect, { initialLoad: true, forceRefresh: true });
    }
    updateCopyButtonsState();
  } catch (e) {
    showRunListError(e.message || 'Failed to load runs');
  } finally {
    setRunListLoading(false);
    updateCopyButtonsState();
  }
}

function escapeHtml(s) {
  if (s == null) return '';
  escapeDiv.textContent = s;
  return escapeDiv.innerHTML;
}

function selectRun(runId, options) {
  const opts = options || {};
  if (runId === currentRunId && !opts.fromPopState && !opts.forceRefresh) return;
  currentRunId = runId;
  if (fetchAbort) {
    fetchAbort.abort();
    fetchAbort = null;
  }
  fetchAbort = new AbortController();
  const signal = fetchAbort.signal;
  if (!opts.fromPopState) {
    setUrlRunId(runId, { replace: !!(opts.fromFallback || opts.initialLoad) });
  }
  runListEl.querySelectorAll('.run-item').forEach((el) => {
    el.classList.toggle('selected', el.dataset.runId === runId);
  });
  if (!opts.fromFallback) hideRunNotFoundBanner();
  updateCopyButtonsState();
  loadRunMeta(runId, signal);
  loadEvents(runId, signal);
}

async function loadRunMeta(runId, signal) {
  try {
    const r = await fetch('/api/runs/' + encodeURIComponent(runId), { signal });
    if (r.status === 404) {
      runHeaderEl.style.display = 'none';
      return;
    }
    if (!r.ok) throw new Error(r.statusText || 'Failed to load run');
    const run = await r.json();
    if (signal?.aborted) return;
    const counts = run.counts || {};
    const parts = [
      run.run_name ? 'Run: ' + run.run_name : '',
      'Status: ' + (run.status || '—'),
      'Started: ' + (run.started_at || '—'),
      run.duration_ms != null ? 'Duration: ' + run.duration_ms + ' ms' : '',
      Object.keys(counts).length ? 'Counts: ' + JSON.stringify(counts) : ''
    ].filter(Boolean);
    runHeaderEl.innerHTML = '<h2>' + escapeHtml(run.run_name || runId.slice(0, 8)) + '</h2><div class="meta">' + escapeHtml(parts.join(' · ')) + '</div>';
    runHeaderEl.style.display = 'block';
  } catch (e) {
    if (e.name === 'AbortError') return;
    runHeaderEl.style.display = 'none';
  }
}

function durationLabel(ms) {
  return ms != null ? ms + ' ms' : '—';
}

function buildEventEl(ev) {
  const isLoop = ev.event_type === 'LOOP_WARNING';
  const isError = ev.event_type === 'ERROR';
  let className = 'event';
  if (isLoop) className += ' loop-warning';
  if (isError) className += ' error';
  const div = document.createElement('div');
  div.className = className;
  div.dataset.eventType = ev.event_type || '';
  const summary = document.createElement('div');
  summary.className = 'event-summary';
  summary.innerHTML = '<span class="toggle">▶</span><span class="type">' + escapeHtml(ev.event_type || '') + '</span><span class="name">' + escapeHtml(ev.name || '') + '</span><span class="duration">' + escapeHtml(durationLabel(ev.duration_ms)) + '</span><span class="ts">' + escapeHtml(ev.ts || '') + '</span>';
  const details = document.createElement('div');
  details.className = 'event-details';
  details.style.display = 'none';
  const payloadStr = JSON.stringify(ev.payload != null ? ev.payload : {}, null, 2);
  const metaStr = JSON.stringify(ev.meta != null ? ev.meta : {}, null, 2);
  details.innerHTML =
    '<div class="row"><span class="label">event_type:</span><pre>' + escapeHtml(ev.event_type || '') + '</pre></div>' +
    '<div class="row"><span class="label">ts:</span><pre>' + escapeHtml(ev.ts || '') + '</pre></div>' +
    '<div class="row"><span class="label">name:</span><pre>' + escapeHtml(ev.name || '') + '</pre></div>' +
    '<div class="row"><span class="label">duration_ms:</span><pre>' + escapeHtml(ev.duration_ms != null ? String(ev.duration_ms) : 'null') + '</pre></div>' +
    '<div class="row"><span class="label">payload:</span><pre>' + escapeHtml(payloadStr) + '</pre></div>' +
    '<div class="row"><span class="label">meta:</span><pre>' + escapeHtml(metaStr) + '</pre></div>';
  summary.addEventListener('click', () => {
    const open = details.style.display !== 'none';
    details.style.display = open ? 'none' : 'block';
    summary.querySelector('.toggle').textContent = open ? '▶' : '▼';
  });
  div.appendChild(summary);
  div.appendChild(details);
  return div;
}

function renderToolbar(events) {
  const n = events.length;
  eventCountEl.textContent = n + ' event' + (n === 1 ? '' : 's');
  const types = [];
  const seen = new Set();
  events.forEach((ev) => {
    const t = ev.event_type || '';
    if (t && !seen.has(t)) { seen.add(t); types.push(t); }
  });
  types.sort();
  filterChipsEl.innerHTML = '';
  const allChip = document.createElement('button');
  allChip.type = 'button';
  allChip.className = 'filter-chip' + (currentFilter === 'all' ? ' active' : '');
  allChip.textContent = 'All';
  allChip.addEventListener('click', () => { currentFilter = 'all'; setFilterActive(); renderEvents(); });
  filterChipsEl.appendChild(allChip);
  types.forEach((t) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'filter-chip' + (currentFilter === t ? ' active' : '');
    btn.textContent = t;
    btn.addEventListener('click', () => { currentFilter = t; setFilterActive(); renderEvents(); });
    filterChipsEl.appendChild(btn);
  });
  timelineToolbarEl.style.display = 'flex';
}

function setFilterActive() {
  filterChipsEl.querySelectorAll('.filter-chip').forEach((el) => {
    const isAll = el.textContent === 'All';
    el.classList.toggle('active', isAll ? currentFilter === 'all' : el.textContent === currentFilter);
  });
}

function renderEvents() {
  const toShow = currentFilter === 'all' ? currentEvents : currentEvents.filter((ev) => (ev.event_type || '') === currentFilter);
  const frag = document.createDocumentFragment();
  toShow.forEach((ev) => frag.appendChild(buildEventEl(ev)));
  timelineEventsEl.innerHTML = '';
  timelineEventsEl.appendChild(frag);
}

async function loadEvents(runId, signal) {
  hideTimelineError();
  timelineEmptyEl.style.display = 'none';
  timelineEventsEl.innerHTML = '<div class="empty">Loading…</div>';
  timelineToolbarEl.style.display = 'none';
  try {
    const r = await fetch('/api/runs/' + encodeURIComponent(runId) + '/events', { signal });
    if (r.status === 404) {
      showRunNotFoundBanner();
      if (fetchAbort) {
        fetchAbort.abort();
        fetchAbort = null;
      }
      if (lastRuns.length > 0) {
        selectRun(lastRuns[0].run_id, { fromFallback: true });
        return;
      }
      const listRes = await fetch('/api/runs', { signal });
      if (listRes.ok) {
        const listData = await listRes.json();
        const runs = listData.runs || [];
        lastRuns = runs;
        if (runs.length > 0) {
          selectRun(runs[0].run_id, { fromFallback: true });
          return;
        }
      }
      showTimelineError('Run not found.');
      return;
    }
    if (!r.ok) throw new Error(r.statusText || 'Failed to load events');
    const data = await r.json();
    if (signal?.aborted) return;
    const events = data.events || [];
    currentEvents = events;
    currentFilter = 'all';
    timelineEventsEl.innerHTML = '';
    if (events.length === 0) {
      timelineEmptyEl.textContent = 'No events for this run.';
      timelineEmptyEl.style.display = 'block';
      return;
    }
    renderToolbar(events);
    renderEvents();
  } catch (e) {
    if (e.name === 'AbortError') return;
    showTimelineError(e.message || 'Failed to load events');
  }
}

window.addEventListener('popstate', () => {
  const runId = getRunIdFromUrl();
  const inList = runId && Array.from(runListEl.querySelectorAll('.run-item')).some((el) => el.dataset.runId === runId);
  if (inList) selectRun(runId, { fromPopState: true });
});

if (btnRefreshEl) btnRefreshEl.addEventListener('click', () => loadRuns());
if (btnCopyLinkEl) btnCopyLinkEl.addEventListener('click', copyRunLink);
if (btnCopyRunIdEl) btnCopyRunIdEl.addEventListener('click', copyRunId);

updateCopyButtonsState();
loadRuns();
