const runListEl = document.getElementById('run-list');
const runListErrorEl = document.getElementById('run-list-error');
const btnRefreshEl = document.getElementById('btn-refresh');
const btnCopyLinkEl = document.getElementById('btn-copy-link');
const btnCopyRunIdEl = document.getElementById('btn-copy-run-id');
const runSummaryEl = document.getElementById('run-summary');
const runSummaryStatusEl = document.getElementById('run-summary-status');
const runSummaryKpisEl = document.getElementById('run-summary-kpis');
const runSummaryCalloutsEl = document.getElementById('run-summary-callouts');
const runSummaryFiltersEl = document.getElementById('run-summary-filters');
const timelineToolbarEl = document.getElementById('timeline-toolbar');
const eventCountEl = document.getElementById('event-count');
const timelineEmptyEl = document.getElementById('timeline-empty');
const timelineErrorEl = document.getElementById('timeline-error');
const timelineEventsEl = document.getElementById('timeline-events');

let currentEvents = [];
let currentFilter = 'all';
let lastRuns = [];
let currentRunId = null;
let currentRunMeta = null;
let fetchAbort = null;
const escapeDiv = document.createElement('div');

// Filter value in URL vs internal event_type. Default All; URL persists so refresh keeps it.
const FILTER_URL_MAP = { all: 'all', llm: 'LLM_CALL', tools: 'TOOL_CALL', errors: 'ERROR', state: 'STATE_UPDATE', loops: 'LOOP_WARNING' };
const FILTER_LABELS = { all: 'All', LLM_CALL: 'LLM', TOOL_CALL: 'Tools', ERROR: 'Errors', STATE_UPDATE: 'State', LOOP_WARNING: 'Loops' };

function getRunIdFromUrl() {
  const url = new URL(window.location.href);
  const q = url.searchParams.get('run') || url.searchParams.get('run_id');
  if (q) return q;
  const parts = url.pathname.split('/').filter(Boolean);
  if (parts.length === 0) return null;
  const last = parts[parts.length - 1];
  const looksLikeId = /^[0-9a-fA-F-]{8,}$/.test(last);
  return looksLikeId ? last : null;
}

function getFilterFromUrl() {
  const url = new URL(window.location.href);
  const q = url.searchParams.get('filter');
  if (!q) return 'all';
  const v = FILTER_URL_MAP[q.toLowerCase()];
  return v != null ? v : 'all';
}

function getRunUrl(runId) {
  if (!runId) return '';
  const url = new URL(window.location.href);
  url.pathname = '/';
  url.searchParams.set('run', runId);
  if (currentFilter !== 'all') url.searchParams.set('filter', getFilterUrlValue(currentFilter));
  return url.toString();
}

function getFilterUrlValue(filterValue) {
  if (filterValue === 'all') return 'all';
  const entry = Object.entries(FILTER_URL_MAP).find(([, v]) => v === filterValue);
  return entry ? entry[0] : 'all';
}

function setUrlRunId(runId, { replace = false } = {}) {
  if (!runId) return;
  const url = new URL(window.location.href);
  url.pathname = '/';
  url.searchParams.set('run', runId);
  url.searchParams.set('filter', getFilterUrlValue(currentFilter));
  const method = replace ? 'replaceState' : 'pushState';
  window.history[method]({ run_id: runId, filter: currentFilter }, '', url.toString());
}

function setUrlFilter(filterValue) {
  const url = new URL(window.location.href);
  url.searchParams.set('filter', getFilterUrlValue(filterValue));
  window.history.replaceState({ run_id: currentRunId, filter: filterValue }, '', url.toString());
}

(function canonicalizeOnBoot() {
  const url = new URL(window.location.href);
  const runIdFromQuery = url.searchParams.get('run') || url.searchParams.get('run_id');
  const runIdFromPath = getRunIdFromUrl();
  const runId = runIdFromQuery || runIdFromPath;
  if (runId) {
    currentFilter = getFilterFromUrl();
    setUrlRunId(runId, { replace: true });
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

// Run Summary panel: single compact overview above the timeline.
// State flow: run.json (loadRunMeta) -> currentRunMeta; events (loadEvents) -> currentEvents.
// We render status strip + KPI chips from run only; callouts (first error, loop warning, running)
// and filter row use events when available. If events fail to load, summary still shows from run.json;
// jump links are hidden when events is null.
function renderRunSummary(run, events) {
  if (!runSummaryEl || !run) {
    if (runSummaryEl) runSummaryEl.style.display = 'none';
    return;
  }
  const counts = run.counts || {};
  const llm = counts.llm_calls != null ? counts.llm_calls : 0;
  const tools = counts.tool_calls != null ? counts.tool_calls : 0;
  const errors = counts.errors != null ? counts.errors : 0;
  const loopWarnings = counts.loop_warnings != null ? counts.loop_warnings : 0;
  const status = (run.status || '').toLowerCase();
  const runName = run.run_name || (run.run_id || currentRunId || '').slice(0, 8);
  const shortId = (run.run_id || currentRunId || '').slice(0, 8);

  // Status strip: badge, run name, started_at, duration, short id + copy
  runSummaryStatusEl.textContent = '';
  const badge = document.createElement('span');
  badge.className = 'status-badge ' + (status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'running');
  badge.textContent = status === 'ok' ? 'OK' : status === 'error' ? 'ERROR' : 'RUNNING';
  runSummaryStatusEl.appendChild(badge);
  const nameSpan = document.createElement('span');
  nameSpan.className = 'run-name';
  nameSpan.textContent = runName;
  runSummaryStatusEl.appendChild(nameSpan);
  const metaSpan = document.createElement('span');
  metaSpan.className = 'run-meta';
  metaSpan.textContent = [run.started_at || '—', run.duration_ms != null ? run.duration_ms + ' ms' : ''].filter(Boolean).join(' · ');
  runSummaryStatusEl.appendChild(metaSpan);
  const idWrap = document.createElement('span');
  idWrap.className = 'run-id-wrap';
  const idText = document.createElement('span');
  idText.textContent = shortId;
  idWrap.appendChild(idText);
  const copyIdBtn = document.createElement('button');
  copyIdBtn.type = 'button';
  copyIdBtn.className = 'btn-copy-id';
  copyIdBtn.textContent = 'Copy';
  copyIdBtn.setAttribute('aria-label', 'Copy run ID');
  copyIdBtn.addEventListener('click', () => copyRunId());
  idWrap.appendChild(copyIdBtn);
  runSummaryStatusEl.appendChild(idWrap);

  // KPI chips
  runSummaryKpisEl.textContent = '';
  ['llm_calls', 'tool_calls', 'errors', 'loop_warnings'].forEach((key) => {
    const label = key === 'llm_calls' ? 'LLM' : key === 'tool_calls' ? 'Tools' : key === 'errors' ? 'Errors' : 'Loop warnings';
    const val = counts[key] != null ? counts[key] : 0;
    const chip = document.createElement('span');
    chip.className = 'kpi-chip';
    const vSpan = document.createElement('span');
    vSpan.className = 'kpi-value';
    vSpan.textContent = String(val);
    chip.appendChild(document.createTextNode(label + ': '));
    chip.appendChild(vSpan);
    runSummaryKpisEl.appendChild(chip);
  });

  // Callouts: only when relevant; jump links only when events available
  runSummaryCalloutsEl.textContent = '';
  if (errors > 0 && Array.isArray(events) && events.length > 0) {
    const firstErrorIdx = events.findIndex((ev) => (ev.event_type || '') === 'ERROR');
    if (firstErrorIdx !== -1) {
      const eventNum = firstErrorIdx + 1;
      const link = document.createElement('button');
      link.type = 'button';
      link.className = 'callout error';
      link.textContent = 'First error at event #' + eventNum;
      link.setAttribute('aria-label', 'Jump to first error, event ' + eventNum);
      link.addEventListener('click', () => jumpToEvent(firstErrorIdx, 'ERROR'));
      runSummaryCalloutsEl.appendChild(link);
    }
  }
  if (loopWarnings > 0 && Array.isArray(events) && events.length > 0) {
    const firstLoopIdx = events.findIndex((ev) => (ev.event_type || '') === 'LOOP_WARNING');
    if (firstLoopIdx !== -1) {
      const eventNum = firstLoopIdx + 1;
      const link = document.createElement('button');
      link.type = 'button';
      link.className = 'callout';
      link.textContent = 'Loop warning detected';
      link.setAttribute('aria-label', 'Jump to first loop warning, event ' + eventNum);
      link.addEventListener('click', () => jumpToEvent(firstLoopIdx, 'LOOP_WARNING'));
      runSummaryCalloutsEl.appendChild(link);
    }
  }
  if (status === 'running') {
    const refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'callout callout-refresh';
    refreshBtn.textContent = 'Run still in progress — Refresh';
    refreshBtn.setAttribute('aria-label', 'Refresh run');
    refreshBtn.addEventListener('click', () => {
      if (currentRunId) {
        const ac = new AbortController();
        loadRunMeta(currentRunId, ac.signal);
        loadEvents(currentRunId, ac.signal);
      }
    });
    runSummaryCalloutsEl.appendChild(refreshBtn);
  }

  // Quick filters row: All, LLM, Tools, Errors, State, Loops; state in URL
  runSummaryFiltersEl.textContent = '';
  const filterValues = ['all', 'LLM_CALL', 'TOOL_CALL', 'ERROR', 'STATE_UPDATE', 'LOOP_WARNING'];
  filterValues.forEach((fv) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'filter-chip' + (currentFilter === fv ? ' active' : '');
    btn.textContent = FILTER_LABELS[fv] || fv;
    btn.addEventListener('click', () => {
      currentFilter = fv;
      setUrlFilter(fv);
      setSummaryFilterActive();
      renderEvents();
    });
    runSummaryFiltersEl.appendChild(btn);
  });

  runSummaryEl.style.display = 'block';
}

function setSummaryFilterActive() {
  if (!runSummaryFiltersEl) return;
  runSummaryFiltersEl.querySelectorAll('.filter-chip').forEach((el, i) => {
    const fv = ['all', 'LLM_CALL', 'TOOL_CALL', 'ERROR', 'STATE_UPDATE', 'LOOP_WARNING'][i];
    el.classList.toggle('active', currentFilter === fv);
  });
}

// Scroll to event at index in currentEvents, expand it, highlight briefly. Filter is set to all so it's visible.
function jumpToEvent(indexInCurrentEvents, eventType) {
  currentFilter = 'all';
  setUrlFilter('all');
  setSummaryFilterActive();
  renderEvents();
  requestAnimationFrame(() => {
    const el = timelineEventsEl.querySelector('[data-event-index="' + indexInCurrentEvents + '"]');
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const summary = el.querySelector('.event-summary');
    const details = el.querySelector('.event-details');
    const toggle = el.querySelector('.toggle');
    if (details && details.style.display !== 'block') {
      details.style.display = 'block';
      if (toggle) toggle.textContent = '▼';
    }
    el.classList.add('highlight');
    setTimeout(() => el.classList.remove('highlight'), 2000);
  });
}

async function loadRunMeta(runId, signal) {
  try {
    const r = await fetch('/api/runs/' + encodeURIComponent(runId), { signal });
    if (r.status === 404) {
      runSummaryEl.style.display = 'none';
      currentRunMeta = null;
      return;
    }
    if (!r.ok) throw new Error(r.statusText || 'Failed to load run');
    const run = await r.json();
    if (signal?.aborted) return;
    currentRunMeta = run;
    renderRunSummary(run, currentEvents.length ? currentEvents : null);
  } catch (e) {
    if (e.name === 'AbortError') return;
    runSummaryEl.style.display = 'none';
    currentRunMeta = null;
  }
}

function durationLabel(ms) {
  return ms != null ? ms + ' ms' : '—';
}

// Build one timeline event element. indexInCurrentEvents is used for jump-to-event (data-event-index).
function buildEventEl(ev, indexInCurrentEvents) {
  const isLoop = ev.event_type === 'LOOP_WARNING';
  const isError = ev.event_type === 'ERROR';
  let className = 'event';
  if (isLoop) className += ' loop-warning';
  if (isError) className += ' error';
  const div = document.createElement('div');
  div.className = className;
  div.dataset.eventType = ev.event_type || '';
  if (indexInCurrentEvents != null) div.dataset.eventIndex = String(indexInCurrentEvents);
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
  timelineToolbarEl.style.display = 'flex';
}

function renderEvents() {
  const frag = document.createDocumentFragment();
  currentEvents.forEach((ev, i) => {
    if (currentFilter === 'all' || (ev.event_type || '') === currentFilter) {
      frag.appendChild(buildEventEl(ev, i));
    }
  });
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
    currentFilter = getFilterFromUrl();
    if (currentRunMeta) renderRunSummary(currentRunMeta, currentEvents);
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
    currentEvents = [];
    if (currentRunMeta) renderRunSummary(currentRunMeta, null);
    showTimelineError(e.message || 'Failed to load events');
  }
}

window.addEventListener('popstate', () => {
  currentFilter = getFilterFromUrl();
  const runId = getRunIdFromUrl();
  const inList = runId && Array.from(runListEl.querySelectorAll('.run-item')).some((el) => el.dataset.runId === runId);
  if (inList) selectRun(runId, { fromPopState: true });
  else {
    setSummaryFilterActive();
    renderEvents();
  }
});

if (btnRefreshEl) btnRefreshEl.addEventListener('click', () => loadRuns());
if (btnCopyLinkEl) btnCopyLinkEl.addEventListener('click', copyRunLink);
if (btnCopyRunIdEl) btnCopyRunIdEl.addEventListener('click', copyRunId);

updateCopyButtonsState();
loadRuns();
