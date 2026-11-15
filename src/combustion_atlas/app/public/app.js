// Combustion Atlas public UI. Self-contained; talks only to this server's /api.
const main = document.querySelector('#main');
const state = {
  me: null, corpus: null, coverage: null, coverageError: '', options: null, optionsError: '',
  ask: { mode: 'answer', question: '', loading: false, error: '', result: null, progress: [], ai: localStorage.getItem('atlas-ai') !== 'off' },
  cov: { x: 'oxygen_pct', y: 'flow_cm_s', slots: [null, null, null], view: 'heatmap', grid: 'flex', facets: {}, cell: null, detail: null, initialized: false },
  predict: { target: '', inputs: {}, loading: false, error: '', result: null },
};
const NAMES = { 'PSI-25': 'BASS-II', 'PSI-26': 'BASS', 'PSI-69': 'FLEX', 'PSI-68': 'FLEX-2', 'PSI-98': 'Saffire-I', 'PSI-99': 'Saffire-II', 'PSI-100': 'Saffire-III', 'PSI-102': 'SAME', 'PSI-101': 'SAME-R' };
const SHAPES = ['circle', 'square', 'triangle'];

// ---------- helpers ----------
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, digits = 3) => v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toLocaleString(undefined, { maximumSignificantDigits: digits });
const count = v => Number(v ?? 0).toLocaleString();
const safeURL = v => { try { const u = new URL(v); return ['https:', 'http:'].includes(u.protocol) ? esc(u.href) : '#'; } catch { return '#'; } };
const docLink = (sourceId, page) => `/api/documents/${encodeURIComponent(sourceId)}${page ? `#page=${encodeURIComponent(page)}` : ''}`;
const invName = id => NAMES[id] ? `${NAMES[id]} (${id})` : id;
async function api(path, options) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  let body = {};
  try { body = await response.json(); } catch { /* non-JSON error page */ }
  if (!response.ok) { const err = new Error(body.error || `Request failed (${response.status})`); err.status = response.status; throw err; }
  return body;
}
const postJSON = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
function route() { const h = location.hash.replace(/^#\/?/, ''); return h.split(/[/?]/)[0] || 'home'; }
const pageHead = (eyebrow, title, lead) => `<header class="page-head"><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>${lead ? `<p>${lead}</p>` : ''}</header>`;
function toast(message) {
  let el = document.querySelector('#toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite'); document.body.append(el); }
  el.textContent = message; el.classList.add('visible');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('visible'), 4000);
}
const emptyBox = (title, text) => `<div class="empty"><h3>${esc(title)}</h3><p>${esc(text)}</p></div>`;

// ---------- data loading ----------
async function loadCoverage() {
  if (state.coverage || state.coverageError) return;
  try { state.coverage = await api('/api/coverage'); }
  catch (e) { state.coverageError = e.status === 503 ? 'Experiment coverage is being prepared and is not available yet.' : e.message; }
}
async function loadOptions() {
  if (state.options || state.optionsError) return;
  try { state.options = await api('/api/predict/options'); }
  catch (e) { state.optionsError = e.status === 503 ? 'Prediction is being prepared and is not available yet.' : e.message; }
}
async function loadCorpus(force = false) {
  if (state.corpus && !force) return;
  try { state.corpus = await api('/api/corpus'); } catch { state.corpus = { documents: [], totals: {} }; }
}

// ---------- shell ----------
function renderShell() {
  const page = route();
  document.querySelectorAll('[data-route]').forEach(a => { if (a.dataset.route === page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  document.querySelectorAll('.admin-only').forEach(el => { el.hidden = !(state.me?.is_admin || state.me?.can_upload); });
  const badge = document.querySelector('#user-badge');
  const hosted = !['127.0.0.1', 'localhost'].includes(location.hostname);
  badge.innerHTML = state.me?.name
    ? `${esc(state.me.name)}${state.me.is_admin ? '<span class="pill">Admin</span>' : ''}${hosted ? ' <a class="small" href="/.auth/logout?post_logout_redirect_uri=/">Sign out</a>' : ''}`
    : state.me?.is_admin ? '<span class="pill">Local admin</span>'
    : hosted ? '<a class="small" href="/.auth/login/github?post_login_redirect_uri=/">Admin sign-in</a>' : '';
  document.querySelector('#site-nav').classList.remove('open');
  document.querySelector('.nav-toggle').setAttribute('aria-expanded', 'false');
}
function render() {
  renderShell();
  const page = route();
  const pages = { home: renderHome, ask: renderAsk, coverage: renderCoverage, predict: renderPredict, sources: renderSources, upload: renderUpload };
  (pages[page] || renderHome)();
  document.title = `${{ home: 'Combustion Atlas', ask: 'Ask', coverage: 'Experiment coverage', predict: 'Prediction', sources: 'Sources', upload: 'Add to corpus' }[page] || 'Combustion Atlas'} · Combustion Atlas`;
}

// ---------- home ----------
function renderHome() {
  const t = state.corpus?.totals || {};
  const runs = state.coverage?.records?.length;
  const stat = (value, label) => `<div class="card stat"><div class="value">${value}</div><div class="label">${label}</div></div>`;
  const tile = (href, icon, title, text) => `<a class="card tile" href="${href}"><span class="tile-icon" aria-hidden="true">${icon}</span><h3>${title}</h3><p>${text}</p><span class="go">Open →</span></a>`;
  main.innerHTML = `
  <section class="hero">
    <div>
      <div class="eyebrow">Built for the NASA Space Apps Challenge 2026</div>
      <h1>Decades of NASA microgravity-combustion research, at your fingertips.</h1>
      <p class="lead">Combustion Atlas makes NASA's spacecraft fire-safety experiments searchable and comparable: every answer quotes the original report and page, and the coverage map shows where the evidence is thin.</p>
      <form class="hero-search" id="hero-search" role="search">
        <label for="hero-q" class="visually-hidden" hidden>Question</label>
        <input id="hero-q" type="search" maxlength="1000" placeholder="e.g. How does opposed-flow velocity affect flame spread?" aria-label="Ask a question">
        <button class="btn primary" type="submit">Ask</button>
      </form>
      <div class="chips hero-try" aria-label="Try asking"><span class="hint" style="margin:0">Try:</span>${HOME_TRY.map(q => `<button type="button" class="chip" data-try="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    </div>
    <div class="hero-art" aria-hidden="true"></div>
  </section>
  <section class="section">
    <div class="grid cols-${state.me?.can_upload ? 4 : 3}">
      ${tile('#/ask', '?', 'Ask a question', 'Get answers built only from indexed NASA documents, with every claim linked to its page. Or plan next research steps.')}
      ${tile('#/coverage', '◎', 'Experiment coverage', 'See which conditions have been tested across investigations, and where this collection has no runs.')}
      ${tile('#/predict', '≈', 'Prediction', 'Enter conditions to find the closest observed runs and a statistical estimate, or “insufficient data”.')}
      ${state.me?.can_upload ? tile('#/upload', '+', 'Add to corpus', state.me?.is_admin ? 'Upload a NASA report or paper (PDF) and review visitor uploads.' : 'Upload a PDF and ask questions about it. It stays private until reviewed.') : ''}
    </div>
  </section>
  <section class="section">
    <div class="section-head"><h2>Data sources</h2><a href="#/sources">View all sources →</a></div>
    <div class="grid cols-5">
      ${stat(count(t.documents), 'Documents')}
      ${stat(count(t.investigations), 'Investigations')}
      ${stat(count(t.pages), 'Pages indexed')}
      ${stat(count(t.figures), 'Figures described')}
      ${stat(runs == null ? '—' : count(runs), 'Experiment runs')}
    </div>
    <p class="hint">Documents come from NASA's Physical Sciences Informatics repository and technical reports. Experiment runs are parsed from PSI experiment tables and are unreviewed candidates.</p>
  </section>`;
  main.querySelectorAll('[data-try]').forEach(b => b.addEventListener('click', () => askQuestion(b.dataset.try)));
  main.querySelector('#hero-search').addEventListener('submit', e => {
    e.preventDefault();
    const q = main.querySelector('#hero-q').value.trim();
    if (!q) return;
    Object.assign(state.ask, { mode: 'answer', question: q });
    location.hash = '#/ask';
    setTimeout(runAsk, 0);
  });
}

// ---------- ask ----------
// Recommended questions, grouped by what they demonstrate. Each was checked against the
// indexed corpus; the last group intentionally shows an honest "not in this collection".
const RECOMMENDED = [
  { group: 'Answers from NASA reports', hint: 'Cited, quoted passages with page links', questions: [
    'Which variables were tested in BASS-II?',
    'How does opposed-flow velocity affect flame spread over thin PMMA?',
    'What did the Saffire experiments show about flame spread on large samples?',
  ] },
  { group: 'Figures', hint: 'AI descriptions of report figures, with the original page image', questions: [
    'Which components are labelled in Figure 5.1 of the BASS-II duct schematic?',
  ] },
  { group: 'Reviewed table records', hint: 'Exact values from human-reviewed tables, with their notes', questions: [
    'What was the initial CO reading for BASS-II test O12?',
    'Which FLEX tables report droplet extinction diameters?',
    'How does adding helium to the atmosphere affect FLEX droplet flames?',
  ] },
  { group: 'Careful answers', hint: 'Partial evidence is scoped, never totalled or guessed', questions: [
    'How many samples were burned in BASS-II?',
  ] },
  { group: 'Honest gaps', hint: 'Says when the collection has no evidence', questions: [
    'What flame spread rates were measured for titanium alloy at Martian surface pressure?',
  ] },
];
const PLAN_EXAMPLES = [
  'Flame spread over thin PMMA at low opposed-flow velocity and reduced oxygen',
  'Flammability limits of PMMA rods in microgravity',
  'Extinction of fuel droplets in helium-diluted atmospheres',
];
const HOME_TRY = [
  'How does opposed-flow velocity affect flame spread over thin PMMA?',
  'What was the initial CO reading for BASS-II test O12?',
  'Which components are labelled in Figure 5.1 of the BASS-II duct schematic?',
  'What did the Saffire experiments show about flame spread on large samples?',
];
function recommendedHTML(mode) {
  const chip = q => `<button type="button" class="chip" data-example="${esc(q)}">${esc(q)}</button>`;
  if (mode === 'plan') return `<div class="chips" aria-label="Example topics">${PLAN_EXAMPLES.map(chip).join('')}</div>`;
  return `<details class="recommended" open><summary>Recommended questions</summary><div class="recommended-groups">${RECOMMENDED.map(g =>
    `<div class="recommended-group"><div class="recommended-title">${esc(g.group)}</div><div class="hint" style="margin:2px 0 8px">${esc(g.hint)}</div><div class="chips">${g.questions.map(chip).join('')}</div></div>`).join('')}</div></details>`;
}
function askQuestion(q) {
  Object.assign(state.ask, { mode: 'answer', question: q });
  location.hash = '#/ask';
  setTimeout(runAsk, 0);
}
function renderAsk() {
  const a = state.ask;
  main.innerHTML = pageHead('Ask', 'Ask the evidence', 'Answers are built only from indexed NASA documents and quote them verbatim. “Plan next steps” lists what the evidence shows, what authors leave open, and grounded suggestions.') + `
  <form class="card ask-form stack" id="ask-form">
    <div class="segmented" role="group" aria-label="Mode">
      <button type="button" data-mode="answer" aria-pressed="${a.mode === 'answer'}">Answer a question</button>
      <button type="button" data-mode="plan" aria-pressed="${a.mode === 'plan'}">Plan next steps</button>
    </div>
    <div><label for="q">${a.mode === 'answer' ? 'Question' : 'Topic or proposed test condition'}</label>
      <textarea id="q" maxlength="1000" required placeholder="${a.mode === 'answer' ? 'Ask about materials, conditions, results or methods…' : 'Describe a topic or proposed experiment…'}">${esc(a.question)}</textarea></div>
    <div class="row ai-row"><span class="ui-switch"><button type="button" class="ui-switch-track" id="ai-toggle" role="switch" aria-checked="${a.ai}" aria-label="AI answers"><span class="ui-switch-knob"></span></button><span class="ui-switch-label${a.ai ? ' active' : ''}">AI answers ${a.ai ? 'on' : 'off'}</span></span>
      <span class="hint" style="margin:0">${a.ai ? 'Uses OpenAI to write a cited answer.' : 'Free keyword search only: no AI calls. Table data and passages are still shown.'}</span></div>
    <div class="row"><button class="btn primary" type="submit" ${a.loading || (a.mode === 'plan' && !a.ai) ? 'disabled' : ''}>${a.loading ? (a.mode === 'answer' ? 'Searching…' : 'Analyzing…') : (a.mode === 'answer' ? (a.ai ? 'Get answer' : 'Search') : 'Find next steps')}</button>
      <span class="hint" style="margin:0">${a.mode === 'plan' && !a.ai ? 'Plan next steps needs AI answers; turn them on above.' : `Takes a few seconds${a.mode === 'plan' ? ' to a minute' : ''}.${a.ai ? limitsHint() : ''}`}</span></div>
    ${recommendedHTML(a.mode)}
  </form>
  <div id="ask-results" class="section" aria-live="polite">${askResults()}</div>`;
  main.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => { if (a.loading) return; state.ask.question = main.querySelector('#q').value; Object.assign(a, { mode: b.dataset.mode, result: null, error: '' }); renderAsk(); }));
  main.querySelector('#ai-toggle').addEventListener('click', () => { if (a.loading) return; a.question = main.querySelector('#q').value; a.ai = !a.ai; localStorage.setItem('atlas-ai', a.ai ? 'on' : 'off'); renderAsk(); });
  main.querySelector('#ask-form').addEventListener('submit', e => { e.preventDefault(); a.question = main.querySelector('#q').value.trim(); runAsk(); });
  main.querySelectorAll('[data-example]').forEach(b => b.addEventListener('click', () => { a.question = b.dataset.example; runAsk(); }));
}
async function runAsk() {
  const a = state.ask;
  if (!a.question || a.loading) return;
  Object.assign(a, { loading: true, error: '', result: null, progress: [] });
  if (route() === 'ask') renderAsk();
  try {
    a.result = a.mode === 'answer'
      ? { kind: 'answer', ...(await streamAnswer(a.question, a.ai)) }
      : { kind: 'plan', ...(await postJSON('/api/directions', { topic: a.question, allow_provider_calls: true })) };
  } catch (e) { a.error = e.message; }
  a.loading = false;
  await loadLimits();
  if (route() === 'ask') renderAsk();
}
// Streams NDJSON progress from /api/ask/stream; falls back to /api/ask when the route is absent.
async function streamAnswer(question, ai = true) {
  // AI off: free keyword search only, no provider calls of any kind.
  const include_sources = myUploads().map(u => u.source_id);
  const body = ai
    ? { question, method: 'hybrid', generate_answer: true, allow_provider_calls: true, include_sources }
    : { question, method: 'keyword', generate_answer: false, allow_provider_calls: false, include_sources };
  const response = await fetch('/api/ask/stream', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (response.status === 404) return postJSON('/api/ask', body);
  if (!response.ok || !response.body) {
    let msg = `Request failed (${response.status})`;
    try { msg = (await response.json()).error || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '', result = null;
  const handle = line => {
    if (!line.trim()) return;
    let event; try { event = JSON.parse(line); } catch { return; }
    if (event.type === 'progress') { state.ask.progress.push(event); updateProgress(); }
    else if (event.type === 'result') { const { type, ...payload } = event; result = payload; }
    else if (event.type === 'error') throw new Error(event.error || 'The request failed.');
  };
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split('\n'); buffer = lines.pop();
    lines.forEach(handle);
    if (done) { handle(buffer); break; }
  }
  if (!result) throw new Error('The answer stream ended before a result arrived.');
  return result;
}
function progressHTML() {
  const steps = state.ask.progress;
  return `<section class="card" aria-label="Progress"><div class="row"><h3 style="margin:0">Working on it</h3><span class="spacer"></span><span class="muted small">${steps.length ? `${fmt(steps[steps.length - 1].elapsed_s, 3)} s` : ''}</span></div>
    <ol class="steps">${steps.length ? steps.map((s, i) => `<li class="${i === steps.length - 1 ? 'current' : 'done'}"><span>${esc(s.message)}</span><span class="muted small">${fmt(s.elapsed_s, 3)} s</span></li>`).join('') : '<li class="current"><span>Starting…</span></li>'}</ol></section>`;
}
// After the answer arrives, keep the steps as a collapsed summary above it.
function stepsSummaryHTML(steps, failed = false) {
  if (!steps?.length) return '';
  const total = fmt(steps[steps.length - 1].elapsed_s, 3);
  const label = failed ? `Stopped after ${total} s` : state.ask.result?.answer ? `Answered in ${total} s` : `Searched in ${total} s`;
  return `<details class="card steps-summary"><summary><span>${failed ? '⚠' : '✓'} ${esc(label)}</span><span class="muted small">${steps.length} step${steps.length === 1 ? '' : 's'}</span></summary>
    <ol class="steps">${steps.map(s => `<li class="done"><span>${esc(s.message)}</span><span class="muted small">${fmt(s.elapsed_s, 3)} s</span></li>`).join('')}</ol></details>`;
}
function updateProgress() { const el = main.querySelector('#ask-results'); if (el && route() === 'ask' && state.ask.loading) el.innerHTML = progressHTML(); }
// ---- Claim display: evidence tag, no label prefixes, near-duplicate quotes grouped ----
const LABEL_PREFIX = /^\s*(?:structured\s+)?(?:document|table(?:\s+record)?|record|figure|visual)(?:\s+description)?\s+evidence\s*[:\-–—]\s*/i;
function quoteTokens(text) {
  return new Set(String(text).toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(w => w.length > 2));
}
function similarQuotes(a, b) {
  const x = quoteTokens(a), y = quoteTokens(b);
  if (!x.size || !y.size) return false;
  let shared = 0; x.forEach(w => { if (y.has(w)) shared += 1; });
  return shared / (x.size + y.size - shared) >= 0.6;
}
function evidenceTag(supports, byId) {
  const sources = supports.map(s => byId[s.chunk_id] || {});
  if (sources.some(src => src.record_card || src.record_row)) return '<span class="pill ok">Table record</span>';
  if (sources.some(src => src.visual)) return '<span class="pill warn">Figure description</span>';
  return '<span class="pill">Report</span>';
}
function sourceLink(support, byId) {
  const src = byId[support.chunk_id] || {};
  if (src.record_card) return esc(src.record_card.locator || src.filename || 'Reviewed evidence');
  return src.source_id ? `<a href="${docLink(src.source_id, src.physical_page)}" target="_blank" rel="noopener noreferrer">${esc(src.filename || 'Source')}, page ${esc(src.physical_page)} ↗</a>` : esc(support.chunk_id);
}
function claimHTML(claim, byId) {
  const groups = [];
  claim.supports.forEach(s => {
    const group = groups.find(g => similarQuotes(g[0].quote, s.quote));
    if (group) group.push(s); else groups.push([s]);
  });
  const body = groups.map(([first, ...rest]) => citeHTML(first, byId) + (rest.length
    ? `<div class="cite also">Also stated in: ${rest.map(s => sourceLink(s, byId)).join(' · ')}</div>` : '')).join('');
  return `<div class="claim"><div class="row" style="gap:8px;align-items:baseline"><p style="margin:0">${esc(String(claim.text).replace(LABEL_PREFIX, ''))}</p>${evidenceTag(claim.supports, byId)}</div>${body}</div>`;
}
function citeHTML(support, byId) {
  const src = byId[support.chunk_id] || {};
  const card = src.record_card;
  const open = Array.isArray(card?.open_questions) ? card.open_questions.length : Number(card?.open_questions || 0);
  const what = card?.kind === 'row' ? `Table row ${card.test_id}` : card?.kind === 'table' ? `Table · ${card.table_title}` : 'Table record';
  const where = card
    ? `<span class="pill ok">${esc(what)}</span>${card.evidence_kind ? ` ${evidencePill(card.evidence_kind)}` : ''} <span>${esc(card.locator || src.filename || 'Reviewed evidence')}</span>${open ? ` · <span class="pill warn">${esc(open)} open question${open === 1 ? '' : 's'}</span>` : ''}`
    : src.source_id ? `<a href="${docLink(src.source_id, src.physical_page)}" target="_blank" rel="noopener noreferrer">${esc(src.filename || 'Source')}, page ${esc(src.physical_page)} ↗</a>` : esc(support.chunk_id);
  const visual = src.visual ? ` · <span class="pill warn">${esc(src.visual.kind)} ${esc(src.visual.label)} · unreviewed AI description</span>` : '';
  const crop = src.visual && String(src.crop_url || '').startsWith('/api/visuals/') ? `<details><summary class="cite">View original page image</summary><img class="crop" loading="lazy" src="${esc(src.crop_url)}" alt="Original page for ${esc(src.visual.kind)} ${esc(src.visual.label)}"></details>` : '';
  return `<blockquote>${esc(support.quote)}</blockquote><div class="cite">${where}${visual}</div>${crop}`;
}
// ---------- reviewed table data (table cards and exact-value rows) ----------
const NOTE_MARK = { ambiguous: '◐', unresolved: '?', pending: '…', assumed: '≈', inferred: '≈', definition: 'i' };
const NOTE_LABEL = { ambiguous: 'Ambiguous', unresolved: 'Unresolved', pending: 'Pending', assumed: 'Assumed', inferred: 'Inferred', definition: 'Definition' };
const EVIDENCE = {
  run: ['Observed run', 'ok'],
  background_table_row: ['Background data · not a run', ''],
  planned_test_condition: ['Proposed test · not run as listed', 'warn'],
};
const prettyField = f => String(f || '').replace(/^condition_/, '').replace(/_/g, ' ');
const evidencePill = kind => { const [label, cls] = EVIDENCE[kind] || ['Table data', '']; return `<span class="pill ${cls}">${esc(label)}</span>`; };
const visibleNotes = notes => (notes || []).filter(n => n.kind !== 'model');
const noteMarks = notes => visibleNotes(notes).map(n => `<span class="note-mark note-${esc(n.kind)}" tabindex="0" title="${esc(`${NOTE_LABEL[n.kind] || n.kind}: ${n.text}`)}" aria-label="${esc(`${NOTE_LABEL[n.kind] || n.kind} note: ${n.text}`)}">${NOTE_MARK[n.kind] || '•'}</span>`).join('');
const tableSourceLink = (r, label) => r.source_id ? `<a class="small" href="${docLink(r.source_id, r.physical_page || null)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : '';
const caveatList = items => (items || []).length ? `<ul class="caveats">${items.map(t => `<li>${esc(t)}</li>`).join('')}</ul>` : '';
function rowHitHTML(r) {
  const c = r.record_card;
  const values = c.values || [];
  const notes = [];
  values.forEach(v => visibleNotes(v.notes).forEach(n => { if (!notes.some(x => x.kind === n.kind && x.text === n.text)) notes.push({ ...n, field: v.field }); }));
  const modelNotes = values.flatMap(v => (v.notes || []).filter(n => n.kind === 'model').map(n => `${prettyField(v.field)}: ${n.text}`));
  const match = (c.match || []).length
    ? `<p class="small" style="margin:6px 0">Matched your values: ${c.match.map(m => `<strong>${esc(m.query)}</strong> → ${esc(prettyField(m.field))}${m.conversion ? ` <span class="pill warn">${esc(m.conversion)}</span>` : ''}`).join(' · ')}</p>`
    : '<p class="small muted" style="margin:6px 0">Named by its test ID in your question.</p>';
  return `<article class="table-hit">
    <div class="row"><span class="pill ok">Table row</span>${evidencePill(c.evidence_kind)}<strong>${esc(c.test_id)}</strong><span class="muted small">${esc(c.table_title || '')}</span><span class="spacer"></span>${tableSourceLink(r, r.physical_page ? `Open page ${r.physical_page}` : 'Open source table')}</div>
    ${c.provenance ? `<p class="provenance">${esc(c.provenance)}</p>` : ''}
    ${match}
    ${caveatList(c.caveats)}
    <div class="table-scroll"><table class="row-values"><thead><tr><th>Field</th><th>Value</th><th>As printed in the source</th></tr></thead><tbody>
      ${values.map(v => `<tr><td>${esc(prettyField(v.field))}</td><td>${esc(v.value ?? '—')}${v.unit ? ` ${esc(v.unit)}` : ''} ${noteMarks(v.notes)}</td><td class="muted">${esc(v.original ?? '')}</td></tr>`).join('')}
    </tbody></table></div>
    ${notes.length ? `<ul class="note-list">${notes.map(n => `<li><span class="note-mark note-${esc(n.kind)}" aria-hidden="true">${NOTE_MARK[n.kind] || '•'}</span><strong>${esc(NOTE_LABEL[n.kind] || n.kind)}</strong> (${esc(prettyField(n.field))}): ${esc(n.text)}</li>`).join('')}</ul>` : ''}
    ${modelNotes.length ? `<details class="small"><summary>All notes, including the model's</summary><ul>${modelNotes.map(t => `<li>${esc(t)}</li>`).join('')}</ul></details>` : ''}
    <p class="muted small" style="margin:4px 0 0">${esc(c.locator || '')}</p>
  </article>`;
}
function tableHitHTML(r) {
  const c = r.record_card;
  const kinds = Object.keys(c.evidence_kinds || {});
  return `<article class="table-hit">
    <div class="row"><span class="pill ok">Table</span>${kinds.map(evidencePill).join('')}<strong>${esc(c.table_title)}</strong><span class="muted small">${count(c.rows)} row${c.rows === 1 ? '' : 's'}</span><span class="spacer"></span>${tableSourceLink(r, 'Open source table')}</div>
    ${c.provenance ? `<p class="provenance">${esc(c.provenance)}</p>` : ''}
    ${caveatList(c.caveats)}
    ${(c.notes || []).length ? `<ul class="note-list">${c.notes.slice(0, 4).map(n => `<li><span class="note-mark note-${esc(n.kind)}" aria-hidden="true">${NOTE_MARK[n.kind] || '•'}</span><strong>${esc(NOTE_LABEL[n.kind] || n.kind)}</strong> (${count(n.rows)} of ${count(c.rows)} rows): ${esc(n.text)}</li>`).join('')}</ul>` : ''}
    <p class="muted small" style="margin:4px 0 0">${esc(c.locator || '')}. To see individual rows, include two or more of a row's exact values in your question.</p>
  </article>`;
}
function tableDataSection(results) {
  const hits = results.filter(r => r.record_card && (r.record_card.kind === 'row' || r.record_card.kind === 'table'));
  if (!hits.length) return '';
  const rows = hits.filter(r => r.record_card.kind === 'row');
  return `<section class="card stack"><div class="section-head"><h3>Reviewed table data</h3><span class="muted small">${rows.length ? `${rows.length} matching row${rows.length === 1 ? '' : 's'} · ` : ''}${hits.length - rows.length} table${hits.length - rows.length === 1 ? '' : 's'}</span></div>
    <p class="muted small" style="margin:0">Values transcribed from NASA tables and reviewed. Marks beside a value (◐ ambiguous, ? unresolved, ≈ assumed or inferred, i definition) carry a note; hover or tap them.</p>
    ${hits.map(r => r.record_card.kind === 'row' ? rowHitHTML(r) : tableHitHTML(r)).join('')}</section>`;
}
function sourcesSummary(allResults) {
  if (!allResults?.length) return '';
  const tableData = tableDataSection(allResults);
  const results = allResults.filter(r => !(r.record_card && (r.record_card.kind === 'row' || r.record_card.kind === 'table')));
  if (!results.length) return tableData;
  const docs = new Set(results.map(r => r.source_id));
  return tableData + `<section class="card"><div class="section-head"><h3>Sources searched</h3><span class="muted small">${results.length} passages · ${docs.size} document${docs.size === 1 ? '' : 's'}</span></div>
    <ul class="source-list">${results.map(r => `<li><div class="row"><strong>${esc(r.filename)}</strong>${r.record_card ? `<span class="pill ok">Table record · ${esc(r.record_card.review_action)}</span>` : `<span class="pill">page ${esc(r.physical_page)}</span>`}${r.visual ? `<span class="pill warn">${esc(r.visual.kind)} ${esc(r.visual.label)} · unreviewed</span>` : ''}${r.investigation_id ? `<span class="pill">${esc(invName(r.investigation_id))}</span>` : ''}<span class="spacer"></span>${r.record_card ? `<span class="small muted">${esc(r.record_card.locator || '')}</span>` : `<a class="small" href="${docLink(r.source_id, r.physical_page)}" target="_blank" rel="noopener noreferrer">Open page ↗</a>`}</div>
      <div class="muted small">${esc(String(r.visual ? r.visual.caption : r.text || '').replace(/\s+/g, ' ').slice(0, 220))}…</div></li>`).join('')}</ul></section>`;
}
function askResults() {
  const a = state.ask;
  if (a.loading) return a.mode === 'answer' ? progressHTML() : '<p class="loading">Reading the evidence and drafting next steps…</p>';
  if (a.error) return stepsSummaryHTML(a.progress, true) + `<div class="error" role="alert">${esc(a.error)}</div>`;
  if (!a.result) return '';
  if (a.result.kind === 'answer' && a.progress.length) return stepsSummaryHTML(a.progress) + askResultBody();
  return askResultBody();
}
function askResultBody() {
  const a = state.ask;
  const results = a.result.results || [];
  const byId = Object.fromEntries(results.map(r => [r.chunk_id, r]));
  if (a.result.kind === 'answer') {
    const ans = a.result.answer;
    const notices = [
      a.result.limited ? `<strong>AI answers are paused.</strong> ${esc(a.result.limited.reason)} Showing free keyword search results below.` : '',
      a.result.answer_unavailable ? `<strong>No AI answer this time.</strong> ${esc(a.result.answer_unavailable)}` : '',
      a.result.retrieval_fallback ? esc(a.result.retrieval_fallback) : '',
      !ans && !a.result.limited && !a.result.answer_unavailable ? '<strong>AI answers are off.</strong> Showing free keyword search results: reviewed table data first, then document passages.' : '',
    ].filter(Boolean);
    const limited = notices.length ? `<section class="card notice" role="status">${notices.join('<br>')}</section>` : '';
    if (!ans) return limited + sourcesSummary(results);
    const partial = ans.status === 'answered' && (ans.limitations || []).length > 0;
    const status = ans.status !== 'answered' ? '<span class="pill bad">Insufficient evidence</span>' : partial ? '<span class="pill warn">Partial evidence</span>' : '<span class="pill ok">Answered from sources</span>';
    const body = ans.status !== 'answered'
      ? `<p>The indexed documents do not support an answer to this question. That means it is missing from this collection, not that it was never studied.</p>`
      : ans.claims.map(c => claimHTML(c, byId)).join('');
    return `<section class="card stack"><div class="row"><h2 style="margin:0">Answer</h2>${status}</div>${body}
      ${(ans.limitations || []).map(l => `<p class="notice">${esc(l)}</p>`).join('')}
      <p class="hint">Every quote is checked against the retrieved text. Verify scientific meaning and numbers against the original page.</p></section>${sourcesSummary(results)}`;
  }
  const d = a.result.directions;
  if (!d || d.status !== 'answered') return `<section class="card"><div class="row"><h2 style="margin:0">Next steps</h2><span class="pill bad">Insufficient evidence</span></div><p>${esc((d?.gaps || [])[0] || 'No indexed passages address this topic.')}</p></section>${sourcesSummary(results)}`;
  const claims = [...d.evidence, ...d.open_questions];
  const claimList = (items, offset) => items.map((c, i) => `<div class="claim" id="claim-${i + offset}"><p><span class="ref">[${i + offset + 1}]</span>${esc(c.text)}</p>${c.supports.map(s => citeHTML(s, byId)).join('')}</div>`).join('');
  const block = (title, hint, content) => `<section class="card stack"><div><h2>${title}</h2><p class="muted small" style="margin:0">${hint}</p></div>${content}</section>`;
  return `<div class="stack">
    <p class="notice">Suggestions are starting points for expert judgment, not validated recommendations or predictions. Each cites the passages it builds on.</p>
    ${block('What the evidence shows', 'Reported conditions, observations and conclusions, quoted from the source.', d.evidence.length ? claimList(d.evidence, 0) : '<p class="muted">No direct findings retrieved.</p>')}
    ${block('Open questions stated by the authors', 'Limitations and future work in the authors’ own words.', d.open_questions.length ? claimList(d.open_questions, d.evidence.length) : '<p class="muted">None stated in the retrieved passages.</p>')}
    ${block('Not found in this collection', 'Aspects of the topic the retrieved passages do not cover. This is not a claim that they are unstudied.', d.gaps.length ? `<ul>${d.gaps.map(g => `<li>${esc(g)}</li>`).join('')}</ul>` : '<p class="muted">No gaps identified.</p>')}
    ${block('Suggested next steps', 'Drafted from the cited items above. Review before acting.', d.suggestions.length ? d.suggestions.map(s => `<div class="suggestion"><span class="pill">${esc(s.kind)}</span><p style="margin:8px 0">${esc(s.text)}</p><span class="cite">Based on ${s.basis.filter(i => i < claims.length).map(i => `<a href="#claim-${i}" data-claim="${i}">[${i + 1}]</a>`).join(' ')}</span></div>`).join('') : '<p class="muted">No suggestions could be grounded in the retrieved evidence.</p>')}
  </div>${sourcesSummary(results)}`;
}
document.addEventListener('click', e => {
  const a = e.target.closest('[data-claim]');
  if (!a) return;
  e.preventDefault();
  document.querySelector(`#claim-${a.dataset.claim}`)?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
});

// ---------- coverage ----------
function niceTicks(lo, hi, n = 6) {
  if (!(Number.isFinite(lo) && Number.isFinite(hi))) return [];
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || mag * 10;
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}
function shapeSVG(shape, x, y, r, cls, fill) {
  const style = fill ? ` style="fill:${fill}"` : '';
  if (shape === 'square') return `<rect class="${cls}" x="${(x - r).toFixed(1)}" y="${(y - r).toFixed(1)}" width="${2 * r}" height="${2 * r}" rx="1.5"${style}/>`;
  if (shape === 'triangle') { const h = r * 1.15; return `<polygon class="${cls}" points="${x},${(y - h).toFixed(1)} ${(x + h).toFixed(1)},${(y + h * .8).toFixed(1)} ${(x - h).toFixed(1)},${(y + h * .8).toFixed(1)}"${style}/>`; }
  return `<circle class="${cls}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}"${style}/>`;
}
const legendShape = (shape, color) => `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">${shapeSVG(shape, 8, 8, 5.5, '', color)}</svg>`;
function slotOf(family) { return state.cov.slots.indexOf(family); }
function initCoverageSelection() {
  const cov = state.coverage, c = state.cov;
  if (c.initialized || !cov) return;
  const fields = (cov.fields || []).filter(f => f.count > 0).map(f => f.key);
  const joint = (a, b) => cov.records.filter(r => Number.isFinite(r[a]) && Number.isFinite(r[b])).length;
  // Prefer O₂ vs flow, but fall back to the axis pair with the most runs plotted together.
  if (!fields.includes(c.x) || !fields.includes(c.y) || joint(c.x, c.y) < 20) {
    let best = [c.x, c.y, -1];
    for (const a of fields) for (const b of fields) if (a !== b) {
      const n = joint(a, b) + (a === 'oxygen_pct' ? 0.5 : 0); // tie-break: O₂ on the horizontal axis
      if (n > best[2]) best = [a, b, n];
    }
    if (best[2] > 0) [c.x, c.y] = best;
  }
  const fams = [...(cov.families || [])].sort((a, b) => b.count - a.count).slice(0, 3);
  fams.forEach((f, i) => { c.slots[i] = f.key; });
  c.initialized = true;
}
function renderCoverage() {
  if (!state.coverage && !state.coverageError) { main.innerHTML = '<p class="loading">Loading experiment coverage…</p>'; loadCoverage().then(() => route() === 'coverage' && renderCoverage()); return; }
  const head = pageHead('Coverage', 'Experiment coverage', 'Where have experiments actually been run? Each heatmap cell counts the runs whose test conditions fall in that range. An empty cell means no runs in this collection, not that a condition is unstudied.');
  if (state.coverageError) { main.innerHTML = head + emptyBox('Not available yet', state.coverageError); return; }
  initCoverageSelection();
  const cov = state.coverage, c = state.cov;
  const viewSwitch = `<div class="segmented" role="group" aria-label="View"><button type="button" data-view="heatmap" aria-pressed="${c.view === 'heatmap'}">Heatmap</button><button type="button" data-view="chart" aria-pressed="${c.view === 'chart'}">Points</button><button type="button" data-view="table" aria-pressed="${c.view === 'table'}">Table</button></div>`;
  if (c.view === 'heatmap' && (cov.grids || []).length) { renderHeatmapPage(head, viewSwitch); return; }
  const fields = (cov.fields || []).filter(f => f.count > 0);
  const fieldOpt = sel => fields.map(f => `<option value="${esc(f.key)}" ${sel === f.key ? 'selected' : ''}>${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''} · ${count(f.count)}</option>`).join('');
  const reviewed = cov.records.filter(r => r.review_status === 'reviewed').length;
  const famChips = (cov.families || []).map(f => {
    const slot = slotOf(f.key);
    const sw = slot >= 0 ? legendShape(SHAPES[slot], `var(--s${slot + 1})`) : legendShape('circle', 'var(--neutral)');
    return `<button type="button" class="chip" data-family="${esc(f.key)}" aria-pressed="${slot >= 0}">${sw}${esc(f.label)} <span class="muted">${count(f.count)}</span></button>`;
  }).join('');
  main.innerHTML = head + `
  <div class="row" style="margin-bottom:16px">${reviewed ? `<span class="pill ok">${count(reviewed)} reviewed</span>` : ''}${(cov.notes || []).filter(n => !/not been reviewed/.test(n)).map(n => `<span class="muted small">${esc(n)}</span>`).join('')}</div>
  <section class="card">
    <div class="controls">
      <div class="field"><label for="cov-x">Horizontal axis</label><select id="cov-x">${fieldOpt(c.x)}</select></div>
      <div class="field"><label for="cov-y">Vertical axis</label><select id="cov-y">${fieldOpt(c.y)}</select></div>
      <span class="spacer"></span>
      ${(cov.proposed || []).length ? `<label class="small" style="display:flex;gap:6px;align-items:center;margin:0"><input type="checkbox" id="cov-proposed" ${c.showProposed === false ? '' : 'checked'}> Show ${count(cov.proposed.length)} proposed FLEX tests</label>` : ''}
      ${viewSwitch}
    </div>
    <div><label>Highlight up to three families</label><div class="chips family-chips" role="group" aria-label="Families">${famChips || '<span class="muted">No families yet.</span>'}</div></div>
    <div id="cov-view" style="margin-top:16px"></div>
  </section>
  <div id="cov-detail" class="section" aria-live="polite"></div>`;
  main.querySelector('#cov-x').addEventListener('change', e => { c.x = e.target.value; drawCoverageView(); });
  main.querySelector('#cov-y').addEventListener('change', e => { c.y = e.target.value; drawCoverageView(); });
  main.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => { c.view = b.dataset.view; renderCoverage(); }));
  main.querySelector('#cov-proposed')?.addEventListener('change', e => { c.showProposed = e.target.checked; drawCoverageView(); });
  main.querySelectorAll('[data-family]').forEach(b => b.addEventListener('click', () => {
    const key = b.dataset.family, slot = slotOf(key);
    if (slot >= 0) c.slots[slot] = null; // freeing a slot never repaints the others
    else { const free = c.slots.indexOf(null); if (free < 0) { toastInline('Three families are highlighted. Deselect one first.'); return; } c.slots[free] = key; }
    renderCoverage();
  }));
  drawCoverageView();
  renderCoverageDetail();
}
// ---------- coverage heatmap (bins and cell classes come from the server) ----------
const CELL_CLASSES = ['strong', 'moderate', 'sparse', 'planned', 'gap'];
const CLASS_LABEL = { strong: 'Strong', moderate: 'Moderate', sparse: 'Sparse', planned: 'Planned only', gap: 'Gap' };
const NOT_RECORDED = 'Not recorded';
function currentGrid() { const gs = state.coverage.grids || []; return gs.find(g => g.key === state.cov.grid) || gs[0]; }
function gridFacets(g) { return (state.cov.facets[g.key] ||= {}); }
function gridView(g) { const f = gridFacets(g); return g.views[g.facets.length ? g.facets.map(x => `${x.key}=${f[x.key] || 'all'}`).join('|') : 'all']; }
const binText = (axis, b) => b.lo != null && axis.unit ? `${b.label} ${axis.unit}` : b.label;
const axisTitle = axis => `${axis.label}${axis.unit ? ` (${axis.unit})` : ''}`;
function cellAt(v, i, j) { return v.cells.find(c => c.x === i && c.y === j) || { x: i, y: j, observed: 0, planned: 0, neighbours: 0, class: 'gap', ids: [], planned_ids: [], outcomes: {}, reviewed: 0 }; }
function cellSummary(g, c) {
  const runs = `${count(c.observed)} run${c.observed === 1 ? '' : 's'}`;
  const planned = c.planned ? `, ${count(c.planned)} planned test${c.planned === 1 ? '' : 's'}` : '';
  return `${axisTitle(g.x).split(' (')[0]} ${binText(g.x, g.x.bins[c.x])}, ${g.y.label.toLowerCase()} ${binText(g.y, g.y.bins[c.y])}: ${runs}${planned}. ${CLASS_LABEL[c.class]}.`;
}
const swatch = cls => `<svg width="22" height="16" aria-hidden="true"><rect class="hm-cell hm-${cls}" x="1" y="1" width="20" height="14" rx="3"/></svg>`;
// The selection is one cell or a whole gap band: { grid, cells: [[x, y], ...], gap? }.
const selectedCells = (c, g) => c.cell && c.cell.grid === g.key ? c.cell.cells : [];

function renderHeatmapPage(head, viewSwitch) {
  const cov = state.coverage, c = state.cov, g = currentGrid();
  const tabs = (cov.grids || []).map(x => `<button type="button" data-grid="${esc(x.key)}" aria-pressed="${x.key === g.key}">${esc(x.label)}</button>`).join('');
  const facets = g.facets.map(f => `<div class="field"><label for="facet-${esc(f.key)}">${esc(f.label)}</label><select id="facet-${esc(f.key)}" data-facet="${esc(f.key)}">${f.options.map(o => `<option value="${esc(o.key)}" ${(gridFacets(g)[f.key] || 'all') === o.key ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select></div>`).join('');
  main.innerHTML = head + `
  <section class="card">
    <div class="controls">
      <div class="field"><label>Investigation family</label><div class="segmented" role="group" aria-label="Investigation family">${tabs}</div></div>
      ${facets}
      <span class="spacer"></span>
      ${viewSwitch}
    </div>
    <p class="muted" style="margin:0 0 12px">${esc(g.description)}</p>
    <div id="cov-view"></div>
  </section>
  <div id="cov-cell" class="section" aria-live="polite"></div>
  <div id="cov-detail" aria-live="polite"></div>`;
  main.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => { c.view = b.dataset.view; renderCoverage(); }));
  main.querySelectorAll('[data-grid]').forEach(b => b.addEventListener('click', () => { c.grid = b.dataset.grid; c.cell = null; c.detail = null; renderCoverage(); }));
  main.querySelectorAll('[data-facet]').forEach(s => s.addEventListener('change', e => { gridFacets(g)[s.dataset.facet] = e.target.value; c.detail = null; if (c.cell?.gap) c.cell = null; drawHeatmap(); renderCellDetail(); renderCoverageDetail(); }));
  drawHeatmap();
  renderCellDetail();
  renderCoverageDetail();
}

function drawHeatmap() {
  const el = main.querySelector('#cov-view'); if (!el) return;
  const g = currentGrid(), v = gridView(g), c = state.cov;
  const nx = g.x.bins.length, ny = g.y.bins.length;
  const longest = Math.max(...g.y.bins.map(b => binText(g.y, b).length));
  const W = 880, mt = 8, mr = 8, mb = 64, ml = Math.min(230, Math.max(84, longest * 7 + 36));
  // "Not recorded" bins sit apart from the real ranges, so they never read as adjacent.
  const SEP = 14, nrX = g.x.bins.some(b => b.key === NOT_RECORDED) ? SEP : 0, nrY = g.y.bins.some(b => b.key === NOT_RECORDED) ? SEP : 0;
  const cw = (W - ml - mr - nrX) / nx, ch = Math.max(34, Math.min(50, 400 / ny)), H = mt + ny * ch + nrY + mb;
  const colX = i => ml + i * cw + (g.x.bins[i].key === NOT_RECORDED ? nrX : 0);
  const nrRow = g.y.bins.findIndex(b => b.key === NOT_RECORDED); // drawn on top; rows below it shift down
  const rowY = j => mt + (ny - 1 - j) * ch + (nrRow >= 0 && j < nrRow ? nrY : 0);
  const sel = new Set(selectedCells(c, g).map(([x, y]) => `${x},${y}`));
  let cells = '';
  for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
    const cell = cellAt(v, i, j), x = colX(i), y = rowY(j);
    const dark = cell.class === 'strong';
    const selected = sel.has(`${i},${j}`);
    cells += `<g class="hm-hit${selected ? ' selected' : ''}" tabindex="0" role="button" data-x="${i}" data-y="${j}" aria-label="${esc(cellSummary(g, cell))}">
      <rect class="hm-cell hm-${cell.class}" x="${(x + 1).toFixed(1)}" y="${(y + 1).toFixed(1)}" width="${(cw - 2).toFixed(1)}" height="${(ch - 2).toFixed(1)}" rx="4"/>
      ${cell.observed ? `<text class="hm-count${dark ? ' on-dark' : ''}" x="${(x + cw / 2).toFixed(1)}" y="${(y + ch / 2 + 5).toFixed(1)}" text-anchor="middle">${count(cell.observed)}</text>` : ''}
      ${cell.planned ? `<text class="hm-planned-count${dark ? ' on-dark' : ''}" x="${(x + cw - 5).toFixed(1)}" y="${(y + ch - 6).toFixed(1)}" text-anchor="end">◇${count(cell.planned)}</text>` : ''}
    </g>`;
  }
  const xLabels = g.x.bins.map((b, i) => {
    const words = b.label.length * 6.6 > cw - 4 ? b.label.split(' ') : [b.label];
    const half = Math.ceil(words.length / 2), lines = words.length > 1 ? [words.slice(0, half).join(' '), words.slice(half).join(' ')] : words;
    return `<text x="${(colX(i) + cw / 2).toFixed(1)}" y="${mt + ny * ch + nrY + 16}" text-anchor="middle">${lines.map((l, k) => `<tspan x="${(colX(i) + cw / 2).toFixed(1)}" dy="${k ? 14 : 0}">${esc(l)}</tspan>`).join('')}</text>`;
  }).join('');
  const yLabels = g.y.bins.map((b, j) => `<text x="${ml - 8}" y="${(rowY(j) + ch / 2 + 4).toFixed(1)}" text-anchor="end">${esc(binText(g.y, b))}</text>`).join('');
  const titles = `<text class="axis-title" x="${(ml + W - mr) / 2}" y="${H - 8}" text-anchor="middle">${esc(axisTitle(g.x))}</text>`;
  const legend = CELL_CLASSES.filter(k => g.has_planned || k !== 'planned').map(k => `<span>${swatch(k)}<strong>${esc(CLASS_LABEL[k])}</strong> <span class="muted">${esc(state.coverage.cell_classes?.[k] || '')}${k === 'planned' ? ' · ◇ = planned tests in a cell' : ''}</span></span>`).join('');
  const t = v.totals;
  const gaps = v.gaps || [];
  const gapItem = (gp, k) => `<li><button type="button" class="gap-pick${c.cell?.gap === k ? ' active' : ''}" data-gap="${k}"><strong>${esc(gp.label)}</strong>${gp.detail ? `<span class="muted"> · ${esc(gp.detail)}</span>` : ''}</button></li>`;
  const gapGroup = (title, status) => { const items = gaps.map((gp, k) => [gp, k]).filter(([gp]) => gp.status === status); return items.length ? `${title ? `<h4>${esc(title)}</h4>` : ''}<ul class="gap-list">${items.map(([gp, k]) => gapItem(gp, k)).join('')}</ul>` : ''; };
  const gapSection = gaps.length ? `<section class="gaps"><h3>Possible experimental gaps</h3><p class="muted small">Condition ranges with no runs in this collection. Click one to highlight it.</p>
    ${g.has_planned ? gapGroup('Planned, not yet run', 'planned') + gapGroup('Neither run nor planned', 'unplanned') : gapGroup('', 'unplanned')}</section>` : '';
  el.innerHTML = `<p class="small" style="margin:0 0 4px"><strong>${count(t.observed)} runs</strong> in ${count(t.cells_with_runs)} of ${count(t.cells)} cells${g.has_planned ? ` · <strong>${count(t.planned)} planned tests</strong>` : ''}</p>
    <p class="y-axis-title">↑ ${esc(axisTitle(g.y))}</p>
    <div class="chart-wrap"><svg class="chart heatmap" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(`${g.label} coverage heatmap: ${g.y.label} by ${g.x.label}`)}">${cells}${xLabels}${yLabels}${titles}</svg><div class="tooltip" id="hm-tip" hidden></div></div>
    <div class="legend" aria-label="Legend">${legend}</div>
    ${gapSection}
    ${(g.notes || []).length ? `<ul class="hint" style="margin-top:12px;padding-left:18px">${g.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}`;
  const tip = el.querySelector('#hm-tip'), svg = el.querySelector('svg');
  const pick = (i, j, gap) => { c.cell = gap == null ? { grid: g.key, cells: [[i, j]] } : { grid: g.key, cells: gaps[gap].cells, gap }; c.detail = null; drawHeatmap(); renderCellDetail(); renderCoverageDetail(); main.querySelector('#cov-cell')?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' }); };
  el.querySelectorAll('.hm-hit').forEach(node => {
    const cell = cellAt(v, +node.dataset.x, +node.dataset.y);
    const show = ev => {
      const box = svg.getBoundingClientRect(), rect = node.getBoundingClientRect();
      const outcomes = Object.entries(cell.outcomes || {}).map(([k, n]) => `${esc(k)} ${count(n)}`).join(', ');
      tip.innerHTML = `<strong>${esc(binText(g.x, g.x.bins[cell.x]))} · ${esc(binText(g.y, g.y.bins[cell.y]))}</strong><br>${count(cell.observed)} run${cell.observed === 1 ? '' : 's'}${outcomes ? ` (${outcomes})` : ''}${cell.planned ? `<br>${count(cell.planned)} planned test${cell.planned === 1 ? '' : 's'}, not runs` : ''}<br><span class="muted">${esc(CLASS_LABEL[cell.class])} · click for details</span>`;
      tip.hidden = false;
      const px = (ev?.clientX ?? rect.left + rect.width / 2) - box.left, py = (ev?.clientY ?? rect.bottom) - box.top;
      tip.style.left = `${Math.max(0, Math.min(px + 14, box.width - 300))}px`; tip.style.top = `${py + 14}px`;
    };
    node.addEventListener('mousemove', show); node.addEventListener('focus', () => show());
    node.addEventListener('mouseleave', () => { tip.hidden = true; }); node.addEventListener('blur', () => { tip.hidden = true; });
    node.addEventListener('click', () => pick(cell.x, cell.y));
    node.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(cell.x, cell.y); } });
  });
  el.querySelectorAll('.gap-pick').forEach(b => b.addEventListener('click', () => pick(null, null, +b.dataset.gap)));
}

function renderCellDetail() {
  const el = main.querySelector('#cov-cell'); if (!el) return;
  const g = currentGrid(), c = state.cov;
  if (!c.cell || c.cell.grid !== g.key) { el.innerHTML = ''; return; }
  const v = gridView(g), members = c.cell.cells.map(([x, y]) => cellAt(v, x, y));
  const gap = c.cell.gap != null ? (v.gaps || [])[c.cell.gap] : null;
  if (c.cell.gap != null && !gap) { el.innerHTML = ''; return; }
  const cell = members.length === 1 ? members[0] : { ids: members.flatMap(m => m.ids), planned_ids: members.flatMap(m => m.planned_ids), outcomes: {}, observed: 0, planned: members.reduce((n, m) => n + m.planned, 0), neighbours: 0, class: gap?.status === 'planned' ? 'planned' : 'gap' };
  const byId = Object.fromEntries(state.coverage.records.map(r => [String(r.id), r]));
  const runs = cell.ids.map(id => byId[String(id)]).filter(Boolean);
  const outcomeOf = r => r.raw?.['Test end'] || (r.outcomes?.burn_time_s?.raw ? `burn time ${r.outcomes.burn_time_s.raw}` : '');
  const cols = [
    ['Material', r => r.raw?.['Fuel Sample Material'] || r.material],
    ['O₂ (%)', r => r.oxygen_pct != null ? fmt(r.oxygen_pct) : null, true],
    ['Pressure (atm)', r => r.pressure_kpa ? fmt(r.pressure_kpa / 101.325) : null, true],
    ['Flow (cm/s)', r => r.flow_cm_s != null ? fmt(r.flow_cm_s) : null, true],
    ['Outcome', outcomeOf],
  ].filter(([, f]) => runs.some(r => f(r)));
  const runTable = runs.length ? `<div class="table-scroll" style="max-height:360px"><table><thead><tr><th>Run</th><th>Investigation</th>${cols.map(([h, , n]) => `<th${n ? ' class="num"' : ''}>${esc(h)}</th>`).join('')}<th>Source</th></tr></thead><tbody>
    ${runs.map(r => `<tr data-row="${esc(r.id)}" tabindex="0" style="cursor:pointer"><td>${esc(r.test_id)}${r.review_status === 'reviewed' ? ' <span class="pill ok">Reviewed</span>' : ''}</td><td>${esc(invName(r.investigation_id))}</td>${cols.map(([, f, n]) => `<td${n ? ' class="num"' : ''}>${esc(f(r) || '—')}</td>`).join('')}<td class="small">${esc(r.source?.file || '')}${r.source?.record != null ? `, record ${esc(r.source.record)}` : ''}</td></tr>`).join('')}
  </tbody></table></div>` : `<p class="muted">No runs in this collection fall in ${gap ? 'this range' : 'this cell'}.</p>`;
  const proposed = cell.planned_ids.map(i => state.coverage.proposed?.[i]).filter(Boolean);
  const plannedTable = proposed.length ? `<h4 style="margin:20px 0 8px">Planned tests · ${count(proposed.length)}</h4><p class="muted small" style="margin:0 0 8px">From the FLEX EIRD test matrices: planned conditions, not runs, with no results.</p>
    <div class="table-scroll" style="max-height:300px"><table><thead><tr><th>Test</th><th>Source</th><th>Fuel</th><th>Added diluent</th><th class="num">O₂ (%)</th><th class="num">Pressure (atm)</th></tr></thead><tbody>
    ${proposed.map(p => `<tr><td>${esc(p.test_id)}</td><td class="small">EIRD Table ${esc(p.table)}, page ${esc(p.page)}</td><td>${esc(({ C7H16: 'Heptane (C₇H₁₆)', CH3OH: 'Methanol (CH₃OH)' })[p.fuel] || p.fuel || '—')}</td><td>${esc(p.suppressant || 'none')}</td><td class="num">${fmt(p.fields?.oxygen_pct)}</td><td class="num">${p.fields?.pressure_kpa != null ? fmt(p.fields.pressure_kpa / 101.325) : '—'}</td></tr>`).join('')}
    </tbody></table></div>` : '';
  const outcomes = Object.entries(cell.outcomes || {});
  const title = gap ? gap.label : `${g.x.label} ${binText(g.x, g.x.bins[cell.x])} · ${g.y.label} ${binText(g.y, g.y.bins[cell.y])}`;
  const pill = gap ? `<span class="pill">Possible gap · ${gap.status === 'planned' ? 'planned, not run' : 'not planned'}</span>` : `<span class="pill">${swatch(cell.class)}${esc(CLASS_LABEL[cell.class])}</span>`;
  // A gap band is described by its overall range on each axis, not cell by cell.
  const span = (axis, idx) => { const bins = [...new Set(idx)].sort((a, b) => a - b).map(k => axis.bins[k]); return bins.every(b => b.lo != null) ? `${axis.label} ${bins[0].lo}–${bins[bins.length - 1].hi}${axis.unit ? ` ${axis.unit}` : ''}` : bins.map(b => b.label).join(', '); };
  const sub = gap
    ? `${esc(span(g.x, members.map(m => m.x)))} · ${esc(span(g.y, members.map(m => m.y)))}${gap.planned ? ` · ${count(gap.planned)} planned test${gap.planned === 1 ? '' : 's'}, no runs` : ' · no runs or planned tests'}`
    : esc(state.coverage.cell_classes?.[cell.class] || '');
  el.innerHTML = `<section class="card"><div class="row"><h3 style="margin:0">${esc(title)}</h3>${pill}<span class="spacer"></span><button class="btn small" type="button" id="close-cell">Close</button></div>
    <p class="muted small" style="margin:8px 0 16px">${sub}</p>
    ${gap ? '' : `<h4 style="margin:0 0 8px">Runs · ${count(runs.length)}</h4>
    ${outcomes.length ? `<p class="small" style="margin:0 0 8px">Outcomes: ${outcomes.map(([k, n]) => `${esc(k)} ${count(n)}`).join(' · ')}</p>` : ''}
    ${runTable}`}${plannedTable}</section>`;
  el.querySelector('#close-cell').addEventListener('click', () => { c.cell = null; c.detail = null; drawHeatmap(); renderCellDetail(); renderCoverageDetail(); });
  bindRows(el);
}
function toastInline(msg) { const el = main.querySelector('#cov-detail'); if (el) el.innerHTML = `<p class="notice">${esc(msg)}</p>`; }
function fieldMeta(key) { return (state.coverage.fields || []).find(f => f.key === key) || { key, label: key, unit: null }; }
const familyLabel = key => (state.coverage.families || []).find(f => f.key === key)?.label || key;
function drawCoverageView() {
  const el = main.querySelector('#cov-view'); if (!el) return;
  const c = state.cov, cov = state.coverage;
  const fx = fieldMeta(c.x), fy = fieldMeta(c.y);
  const plotted = cov.records.filter(r => Number.isFinite(r[c.x]) && Number.isFinite(r[c.y]));
  const missing = cov.records.length - plotted.length;
  // Proposed FLEX tests: a separate layer that never affects gaps.
  const proposed = c.showProposed === false ? [] : (cov.proposed || []).filter(p => Number.isFinite(p.fields?.[c.x]) && Number.isFinite(p.fields?.[c.y]));
  if (c.view === 'table') { el.innerHTML = coverageTable(cov.records); bindRows(el); return; }
  if (!plotted.length) { el.innerHTML = emptyBox('Nothing to plot', `No runs have both ${fx.label} and ${fy.label}. Try other axes or the table view.`); return; }
  const W = 880, H = 500, m = { l: 64, r: 20, t: 16, b: 56 };
  const gaps = (cov.gaps || []).filter(g => (g.x_field === c.x && g.y_field === c.y) || (g.x_field === c.y && g.y_field === c.x))
    .map(g => g.x_field === c.x ? g : { ...g, x_range: g.y_range, y_range: g.x_range });
  const xs = [...plotted.map(r => r[c.x]), ...proposed.map(p => p.fields[c.x]), ...gaps.flatMap(g => g.x_range)], ys = [...plotted.map(r => r[c.y]), ...proposed.map(p => p.fields[c.y]), ...gaps.flatMap(g => g.y_range)];
  const pad = (lo, hi) => { const d = (hi - lo) || Math.abs(hi) || 1; return [lo - d * .06, hi + d * .06]; };
  const [x0, x1] = pad(Math.min(...xs), Math.max(...xs)), [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
  const sx = v => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), sy = v => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  const xt = niceTicks(x0, x1), yt = niceTicks(y0, y1);
  const grid = `<g class="grid">${xt.map(v => `<line x1="${sx(v)}" x2="${sx(v)}" y1="${m.t}" y2="${H - m.b}"/>`).join('')}${yt.map(v => `<line x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/>`).join('')}</g>`;
  const axes = `<line class="axis-line" x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}"/><line class="axis-line" x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${H - m.b}"/>
    ${xt.map(v => `<text x="${sx(v)}" y="${H - m.b + 18}" text-anchor="middle">${fmt(v)}</text>`).join('')}
    ${yt.map(v => `<text x="${m.l - 8}" y="${sy(v) + 4}" text-anchor="end">${fmt(v)}</text>`).join('')}
    <text class="axis-title" x="${(m.l + W - m.r) / 2}" y="${H - 12}" text-anchor="middle">${esc(fx.label)}${fx.unit ? ` (${esc(fx.unit)})` : ''}</text>
    <text class="axis-title" transform="translate(16 ${(m.t + H - m.b) / 2}) rotate(-90)" text-anchor="middle">${esc(fy.label)}${fy.unit ? ` (${esc(fy.unit)})` : ''}</text>`;
  const gapSVG = gaps.map((g, i) => { const xa = sx(g.x_range[0]), xb = sx(g.x_range[1]), ya = sy(g.y_range[1]), yb = sy(g.y_range[0]); return `<rect class="gap-rect" x="${Math.min(xa, xb)}" y="${Math.min(ya, yb)}" width="${Math.abs(xb - xa)}" height="${Math.abs(yb - ya)}" rx="4"/><text class="gap-label" x="${Math.min(xa, xb) + 6}" y="${Math.min(ya, yb) + 16}">Gap ${i + 1}</text>`; }).join('');
  const order = [...plotted].sort((a, b) => (slotOf(a.family) >= 0) - (slotOf(b.family) >= 0)); // highlighted on top
  const marks = order.map(r => {
    const slot = slotOf(r.family), x = sx(r[c.x]), y = sy(r[c.y]);
    const cls = `pt${r.review_status === 'reviewed' ? ' reviewed' : ''}`;
    const shape = slot >= 0 ? shapeSVG(SHAPES[slot], x, y, 5.5, cls, `var(--s${slot + 1})`) : shapeSVG('circle', x, y, 4, cls, 'var(--neutral)');
    return `<g class="hit" tabindex="0" role="button" data-id="${esc(r.id)}" aria-label="${esc(`${familyLabel(r.family)} ${r.test_id}: ${fx.label} ${fmt(r[c.x])}, ${fy.label} ${fmt(r[c.y])}`)}">${shape}<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="11" fill="transparent"/></g>`;
  }).join('');
  const diamond = (x, y, r) => `${x},${(y - r).toFixed(1)} ${(x + r).toFixed(1)},${y} ${x},${(y + r).toFixed(1)} ${(x - r).toFixed(1)},${y}`;
  const proposedSVG = proposed.map((p, i) => { const x = sx(p.fields[c.x]), y = sy(p.fields[c.y]); return `<g class="hit-proposed" tabindex="0" role="button" data-pid="${i}" aria-label="${esc(`Proposed test ${p.test_id}, not run as listed: ${fx.label} ${fmt(p.fields[c.x])}, ${fy.label} ${fmt(p.fields[c.y])}`)}"><polygon class="proposed-mark" points="${diamond(x, y, 6)}"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="10" fill="transparent"/></g>`; }).join('');
  const legendItems = state.cov.slots.map((k, i) => k ? `<span>${legendShape(SHAPES[i], `var(--s${i + 1})`)}${esc(familyLabel(k))}</span>` : '').join('') + `<span>${legendShape('circle', 'var(--neutral)')}Other families</span><span><svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="var(--neutral)" stroke="var(--ink)" stroke-width="2"/></svg>Reviewed (dark ring)</span>${gaps.length ? '<span><svg width="22" height="14" aria-hidden="true"><rect x="1" y="1" width="20" height="12" rx="3" fill="none" stroke="var(--ink-2)" stroke-dasharray="4 3"/></svg>No runs in this collection</span>' : ''}${proposed.length ? '<span><svg width="16" height="16" aria-hidden="true"><polygon class="proposed-mark" points="8,2 14,8 8,14 2,8"/></svg>Proposed FLEX test (planned, not run as listed; no results)</span>' : ''}`;
  el.innerHTML = `<div class="chart-wrap"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Scatter of ${plotted.length} runs: ${fy.label} against ${fx.label}`)}">${grid}${gapSVG}${axes}${proposedSVG}${marks}</svg><div class="tooltip" id="cov-tip" hidden></div></div>
    <div class="legend" aria-label="Legend">${legendItems}</div>
    ${missing ? `<p class="hint">${count(missing)} runs lack ${esc(fx.label)} or ${esc(fy.label)} and are not plotted; they appear in the table view.</p>` : ''}
    ${gaps.length ? `<ol class="small" style="margin-top:12px">${gaps.map(g => `<li>${esc(g.note)}</li>`).join('')}</ol>` : ''}`;
  const tip = el.querySelector('#cov-tip'), svg = el.querySelector('svg');
  const byId = Object.fromEntries(cov.records.map(r => [String(r.id), r]));
  el.querySelectorAll('.hit').forEach(g => {
    const r = byId[g.dataset.id];
    const show = ev => {
      const box = svg.getBoundingClientRect();
      tip.innerHTML = `<strong>${esc(familyLabel(r.family))} · ${esc(r.test_id)}</strong><br>${esc(fx.label)}: ${fmt(r[c.x])}${fx.unit ? ` ${esc(fx.unit)}` : ''}<br>${esc(fy.label)}: ${fmt(r[c.y])}${fy.unit ? ` ${esc(fy.unit)}` : ''}${r.material ? `<br>Material: ${esc(r.material)}` : ''}<br><span class="muted">${r.review_status === 'reviewed' ? 'Reviewed · ' : ''}click for details</span>`;
      tip.hidden = false;
      const rect = g.getBoundingClientRect();
      const px = (ev?.clientX ?? rect.left + rect.width / 2) - box.left, py = (ev?.clientY ?? rect.top) - box.top;
      tip.style.left = `${Math.max(0, Math.min(px + 14, box.width - 300))}px`; tip.style.top = `${py + 14}px`;
    };
    g.addEventListener('mousemove', show); g.addEventListener('focus', () => show());
    g.addEventListener('mouseleave', () => { tip.hidden = true; }); g.addEventListener('blur', () => { tip.hidden = true; });
    const open = () => { state.cov.detail = r.id; renderCoverageDetail(); };
    g.addEventListener('click', open); g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  });
  el.querySelectorAll('.hit-proposed').forEach(g => {
    const p = proposed[Number(g.dataset.pid)];
    const show = ev => {
      const box = svg.getBoundingClientRect(), rect = g.getBoundingClientRect();
      tip.innerHTML = `<strong>Proposed test · ${esc(p.test_id)}</strong> (EIRD Table ${esc(p.table)}, page ${esc(p.page)})<br>${esc(fx.label)}: ${fmt(p.fields[c.x])}${fx.unit ? ` ${esc(fx.unit)}` : ''}<br>${esc(fy.label)}: ${fmt(p.fields[c.y])}${fy.unit ? ` ${esc(fy.unit)}` : ''}${p.fuel ? `<br>Fuel: ${esc(p.fuel)}` : ''}${p.suppressant ? ` · suppressant: ${esc(p.suppressant)}` : ''}<br><span class="muted">${esc(p.conversions.join('; '))}</span><br><span class="muted">Planned in a test matrix, not run as listed; no results.</span>`;
      tip.hidden = false;
      const px = (ev?.clientX ?? rect.left + rect.width / 2) - box.left, py = (ev?.clientY ?? rect.top) - box.top;
      tip.style.left = `${Math.max(0, Math.min(px + 14, box.width - 300))}px`; tip.style.top = `${py + 14}px`;
    };
    g.addEventListener('mousemove', show); g.addEventListener('focus', () => show());
    g.addEventListener('mouseleave', () => { tip.hidden = true; }); g.addEventListener('blur', () => { tip.hidden = true; });
  });
}
function coverageTable(records) {
  const cols = ['oxygen_pct', 'flow_cm_s', 'pressure_kpa'].map(fieldMeta);
  return `<div class="table-scroll"><table><caption class="visually-hidden" hidden>Experiment runs</caption><thead><tr><th>Family</th><th>Test</th><th>Material</th>${cols.map(f => `<th class="num">${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''}</th>`).join('')}<th>Gravity</th><th>Status</th><th>Source</th></tr></thead><tbody>
    ${records.map(r => `<tr data-row="${esc(r.id)}" tabindex="0" style="cursor:pointer"><td>${esc(familyLabel(r.family))}</td><td>${esc(r.test_id)}</td><td>${esc(r.material || '—')}</td>${cols.map(f => `<td class="num">${fmt(r[f.key])}</td>`).join('')}<td>${esc(r.gravity || '—')}</td><td>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : ''}</td><td class="small">${esc(r.source?.file || '')}${r.source?.record != null ? `, record ${esc(r.source.record)}` : ''}</td></tr>`).join('')}
  </tbody></table></div>`;
}
function bindRows(el) { el.querySelectorAll('[data-row]').forEach(tr => { const open = () => { state.cov.detail = tr.dataset.row; renderCoverageDetail(); }; tr.addEventListener('click', open); tr.addEventListener('keydown', e => { if (e.key === 'Enter') open(); }); }); }
function renderCoverageDetail() {
  const el = main.querySelector('#cov-detail'); if (!el) return;
  const r = state.coverage.records.find(x => String(x.id) === String(state.cov.detail));
  if (!r) { el.innerHTML = ''; return; }
  const row = (k, v) => v == null || v === '' ? '' : `<dt>${esc(k)}</dt><dd>${v}</dd>`;
  const outcomes = Object.entries(r.outcomes || {});
  el.innerHTML = `<section class="card"><div class="row"><h3 style="margin:0">${esc(familyLabel(r.family))} · ${esc(r.test_id)}</h3>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : ''}<span class="spacer"></span><button class="btn small" type="button" id="close-detail">Close</button></div>
    <dl class="kv" style="margin-top:16px">${row('Investigation', esc(invName(r.investigation_id)))}${row('Material', esc(r.material))}${row('Geometry', esc(r.geometry))}${row('Oxygen', r.oxygen_pct != null ? `${fmt(r.oxygen_pct)} %` : null)}${row('Flow', r.flow_cm_s != null ? `${fmt(r.flow_cm_s)} cm/s` : null)}${row('Pressure', r.pressure_kpa != null ? `${fmt(r.pressure_kpa)} kPa` : null)}${row('Gravity', esc(r.gravity))}
    ${outcomes.map(([k, o]) => row(k.replaceAll('_', ' '), `${o.value != null ? fmt(o.value) : '—'}${o.unit ? ` ${esc(o.unit)}` : ''} <span class="muted small">(source text: “${esc(o.raw)}”)</span>`)).join('')}
    ${row('Source', `${esc(r.source?.file || '')}${r.source?.record != null ? `, record ${esc(r.source.record)}` : ''}`)}</dl></section>`;
  el.querySelector('#close-detail').addEventListener('click', () => { state.cov.detail = null; renderCoverageDetail(); });
}

// ---------- prediction ----------
function renderPredict() {
  if (!state.options && !state.optionsError) { main.innerHTML = '<p class="loading">Loading prediction options…</p>'; loadOptions().then(() => route() === 'predict' && renderPredict()); return; }
  const head = pageHead('Prediction', 'Estimate an outcome from similar runs', 'Enter test conditions to see the closest observed runs and a statistical estimate. When the data cannot support an estimate, it says so.');
  if (state.optionsError) { main.innerHTML = head + emptyBox('Not available yet', state.optionsError); return; }
  const o = state.options, p = state.predict;
  if (!o.targets?.length) { main.innerHTML = head + emptyBox('No outcomes to estimate yet', 'Prediction needs experiment runs with measured outcomes.'); return; }
  if (!p.target) p.target = o.targets[0].key;
  const field = f => {
    const id = `f-${f.key}`, v = p.inputs[f.key] ?? '';
    const control = f.kind === 'category'
      ? `<select id="${id}" data-input="${esc(f.key)}"><option value="">Any</option>${(f.values || []).map(x => `<option ${String(v) === String(x) ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`
      : `<input id="${id}" data-input="${esc(f.key)}" type="number" step="any" inputmode="decimal" value="${esc(v)}" placeholder="${f.min != null ? `${fmt(f.min)}–${fmt(f.max)}` : ''}">`;
    return `<div class="field"><label for="${id}">${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''}</label>${control}${f.kind !== 'category' && f.min != null ? `<div class="hint">Observed range ${fmt(f.min)}–${fmt(f.max)}</div>` : ''}</div>`;
  };
  main.innerHTML = head + `
  <p class="notice warn">Statistical estimate from unreviewed candidate data. Not a validated prediction; do not use it for safety decisions.</p>
  <div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);margin-top:16px">
    <form class="card" id="predict-form">
      <div class="field"><label for="target">Outcome to estimate</label><select id="target">${o.targets.map(t => `<option value="${esc(t.key)}" ${p.target === t.key ? 'selected' : ''}>${esc(t.label)}${t.unit ? ` (${esc(t.unit)})` : ''} · ${count(t.n)} runs</option>`).join('')}</select></div>
      ${(o.features || []).map(field).join('')}
      <button class="btn primary" type="submit" ${p.loading ? 'disabled' : ''}>${p.loading ? 'Estimating…' : 'Estimate'}</button>
    </form>
    <div id="predict-result" aria-live="polite">${predictResult()}</div>
  </div>`;
  const form = main.querySelector('#predict-form');
  form.querySelector('#target').addEventListener('change', e => { p.target = e.target.value; });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    p.inputs = {};
    form.querySelectorAll('[data-input]').forEach(el => { if (el.value !== '') p.inputs[el.dataset.input] = el.type === 'number' ? Number(el.value) : el.value; });
    Object.assign(p, { loading: true, error: '', result: null }); renderPredict();
    try { p.result = await postJSON('/api/predict', { target: p.target, inputs: p.inputs }); } catch (err) { p.error = err.message; }
    p.loading = false; if (route() === 'predict') renderPredict();
  });
}
function predictResult() {
  const p = state.predict;
  if (p.loading) return '<p class="loading">Finding similar runs…</p>';
  if (p.error) return `<div class="error" role="alert">${esc(p.error)}</div>`;
  if (!p.result) return emptyBox('Enter conditions', 'Results show the closest observed runs and, when supported, a model estimate.');
  const r = p.result, mdl = r.model || {}, t = (state.options.targets || []).find(x => x.key === r.target) || { label: r.target };
  const unit = t.unit ? ` ${esc(t.unit)}` : '';
  const model = mdl.status === 'ok'
    ? `<section class="card stack"><div class="eyebrow" style="margin:0">Model estimate · ${esc(t.label)}</div>
        <div class="result-hero"><span class="big">${fmt(mdl.prediction)}</span><span class="muted">${unit}</span>${mdl.interval ? `<span class="pill">likely ${fmt(mdl.interval[0])}–${fmt(mdl.interval[1])}${unit}</span>` : ''}</div>
        ${mdl.in_domain ? '' : '<p class="notice warn">These conditions are outside the range the model was trained on. Treat the estimate as unreliable.</p>'}
        <dl class="kv"><dt>Cross-validated error (MAE)</dt><dd>${fmt(mdl.cv_mae)}${unit}</dd><dt>Training runs</dt><dd>${count(mdl.n_train)}</dd><dt>Inputs used</dt><dd>${esc((mdl.features || []).join(', ') || '—')}</dd><dt>Within training range</dt><dd>${mdl.in_domain ? 'Yes' : 'No'}</dd></dl></section>`
    : `<section class="insufficient" role="status"><h3>Insufficient data</h3><p style="margin:0 0 8px">${esc(mdl.reason || 'There are not enough comparable runs to estimate this outcome.')}</p><span class="small">Training runs available: ${count(mdl.n_train || 0)}</span></section>`;
  const near = (r.nearest || []).map(n => { const rec = n.record, out = rec.outcomes?.[r.target];
    return `<tr><td class="num">${fmt(n.distance, 2)}</td><td>${esc(familyLabelSafe(rec))} · ${esc(rec.test_id)}</td><td class="num">${fmt(rec.oxygen_pct)}</td><td class="num">${fmt(rec.flow_cm_s)}</td><td class="num">${fmt(rec.pressure_kpa)}</td><td class="num">${out ? `${fmt(out.value)}${out.unit ? ` ${esc(out.unit)}` : ''}` : '—'}</td></tr>`; }).join('');
  return `<div class="stack">${model}
    <section class="card"><h3>Closest observed runs</h3><p class="muted small">Smaller distance means more similar conditions (standardized units). These are measurements, not estimates.</p>
      ${near ? `<div class="table-scroll"><table><thead><tr><th class="num">Distance</th><th>Run</th><th class="num">O₂ (%)</th><th class="num">Flow (cm/s)</th><th class="num">Pressure (kPa)</th><th class="num">${esc(t.label)}</th></tr></thead><tbody>${near}</tbody></table></div>` : '<p class="muted">No comparable runs found.</p>'}</section>
    ${(r.notes || []).map(n => `<p class="hint">${esc(n)}</p>`).join('')}</div>`;
}
function familyLabelSafe(rec) { return state.coverage ? familyLabel(rec.family) : (rec.family || invName(rec.investigation_id)); }

// ---------- sources ----------
function renderSources() {
  if (!state.corpus) { main.innerHTML = '<p class="loading">Loading sources…</p>'; Promise.all([loadCorpus(), loadCoverage()]).then(() => route() === 'sources' && renderSources()); return; }
  const docs = state.corpus.documents || [];
  const fams = state.coverage?.families || [];
  main.innerHTML = pageHead('Sources', 'What the atlas draws on', 'Documents are indexed page by page; experiment runs come from PSI experiment tables. Open any document at its original pages.') + `
  <section class="section"><div class="section-head"><h2>Documents</h2><span class="muted small">${count(docs.length)} documents</span></div>
    ${docs.length ? `<div class="grid cols-3">${docs.map(d => `<article class="card stack"><h3 style="overflow-wrap:anywhere">${esc(d.filename)}</h3><div class="row">${(d.investigation_ids || []).map(i => `<span class="pill">${esc(invName(i))}</span>`).join('')}</div>
      <p class="muted small" style="margin:0">${count(d.pages)} pages · ${count(d.passages)} passages · ${count(d.figures)} figures${d.tables ? ` · ${count(d.tables)} tables` : ''}</p>
      <div class="row"><a class="btn small" href="${docLink(d.source_id)}" target="_blank" rel="noopener noreferrer">Open PDF ↗</a>${d.source_url ? `<a class="btn small" href="${safeURL(d.source_url)}" target="_blank" rel="noopener noreferrer">Source record ↗</a>` : ''}</div></article>`).join('')}</div>` : emptyBox('No documents yet', 'Documents will appear here once indexed.')}
  </section>
  <section class="section"><div class="section-head"><h2>Experiment tables</h2><span class="muted small">${state.coverageError ? 'not available yet' : `${count(fams.length)} families`}</span></div>
    ${fams.length ? `<div class="table-scroll"><table><thead><tr><th>Family</th><th>Investigations</th><th class="num">Runs</th></tr></thead><tbody>${fams.map(f => `<tr><td>${esc(f.label)}</td><td>${(f.investigation_ids || []).map(i => esc(invName(i))).join(', ')}</td><td class="num">${count(f.count)}</td></tr>`).join('')}</tbody></table></div>` : emptyBox('No experiment tables yet', state.coverageError || 'Experiment runs will appear once parsed.')}
  </section>`;
}

// ---------- upload (admin) ----------
// Visitor uploads are remembered in this browser so their questions can include them.
const UPLOADS_KEY = 'combustionAtlas.myUploads';
function myUploads() {
  try { return JSON.parse(localStorage.getItem(UPLOADS_KEY) || '[]').slice(-10); } catch { return []; }
}
function rememberUpload(source_id, filename) {
  const list = myUploads().filter(u => u.source_id !== source_id);
  list.push({ source_id, filename });
  localStorage.setItem(UPLOADS_KEY, JSON.stringify(list.slice(-10)));
}
function renderUpload() {
  const me = state.me || {};
  const limits = me.upload_limits || {};
  if (!me.can_upload) {
    main.innerHTML = pageHead('Contribute', 'Add to corpus', 'Upload a NASA report or paper (PDF).') + emptyBox('Uploads are closed', 'Only the project administrator can add documents right now.');
    return;
  }
  const visitor = !me.is_admin;
  const head = visitor
    ? pageHead('Contribute', 'Add a document', 'Upload a PDF and ask questions about it. It is private to you (this browser) until an administrator reviews it and adds it to the shared collection.')
    : pageHead('Administrator', 'Add to corpus', 'Upload a NASA report or paper (PDF). Pages are extracted and added without changing existing documents.');
  const mine = myUploads();
  main.innerHTML = head + `
  <form class="card" id="upload-form" style="max-width:720px">
    <div class="field"><label for="u-file">PDF file (${visitor ? `up to ${esc(limits.max_mb)} MB and ${esc(limits.max_pages)} pages` : 'up to 80 MB'})</label><input id="u-file" type="file" accept="application/pdf,.pdf" required></div>
    ${visitor ? '' : `<div class="field"><label for="u-inv">Investigation ID</label><input id="u-inv" required maxlength="79" placeholder="e.g. PSI-25 or SAFFIRE-II" style="width:100%"></div>
    <div class="field"><label for="u-url">Source URL (optional)</label><input id="u-url" type="url" placeholder="https://ntrs.nasa.gov/citations/…" style="width:100%"></div>
    <div class="field"><label class="check"><input id="u-embed" type="checkbox" checked><span>Enable semantic search (creates vector embeddings so passages can be found by meaning, not just keywords)</span></label></div>`}
    ${visitor && me.upload_code_required ? '<div class="field"><label for="u-code">Upload code</label><input id="u-code" type="password" autocomplete="off" required style="width:100%"></div>' : ''}
    <button class="btn primary" type="submit">${visitor ? 'Upload and index' : 'Add to corpus'}</button>
    <p class="hint">${visitor
      ? `Each visitor can upload ${esc(limits.per_day)} documents per day${limits.remaining_today != null ? ` (${esc(limits.remaining_today)} left today)` : ''}; uploads also count toward the site's daily AI limit. Text is extracted and indexed for semantic search; figures are not described.`
      : 'Figures are not described automatically yet; text search and cited answers work immediately.'}</p>
    <div id="u-status" aria-live="polite"></div>
  </form>
  ${visitor && mine.length ? `<section class="card section" style="max-width:720px"><h3 style="margin-top:0">Your uploads (included in your questions)</h3><ul class="plain">${mine.map(u => `<li>${esc(u.filename || u.source_id)}</li>`).join('')}</ul><p class="hint">Only questions from this browser search these documents.</p></section>` : ''}
  ${visitor ? '' : '<section class="section" id="pending-uploads"><p class="loading">Loading visitor uploads…</p></section>'}`;
  const form = main.querySelector('#upload-form');
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const file = form.querySelector('#u-file').files[0], status = form.querySelector('#u-status'), button = form.querySelector('button[type=submit]');
    if (!file) return;
    const maxBytes = (visitor ? limits.max_mb : 80) * 1024 * 1024;
    if (file.size > maxBytes) { status.innerHTML = `<div class="error">The PDF is larger than ${visitor ? limits.max_mb : 80} MB.</div>`; return; }
    const params = new URLSearchParams({ filename: file.name });
    if (!visitor) {
      params.set('investigation', form.querySelector('#u-inv').value.trim());
      params.set('source_url', form.querySelector('#u-url').value.trim());
      params.set('embed', form.querySelector('#u-embed').checked ? '1' : '0');
    }
    const headers = { 'Content-Type': 'application/pdf' };
    const code = form.querySelector('#u-code');
    if (code) headers['X-Upload-Code'] = code.value;
    button.disabled = true; status.innerHTML = '<p class="loading" style="padding:16px 0">Extracting and indexing pages…</p>';
    try {
      const r = await api(`/api/upload?${params}`, { method: 'POST', headers, body: file });
      if (r.quarantined) {
        rememberUpload(r.source_id, r.filename);
        state.me = await api('/api/me');
        status.innerHTML = `<p class="notice">Indexed <strong>${esc(r.filename)}</strong>: ${esc(r.physical_pages)} pages, ${esc(r.chunks_added)} passages. It is private to this browser until reviewed. ${esc(r.uploads_left_today)} upload${r.uploads_left_today === 1 ? '' : 's'} left today.</p><button class="btn" type="button" id="ask-upload">Ask about this document →</button>`;
        status.querySelector('#ask-upload').addEventListener('click', () => { state.ask.question = ''; location.hash = '#/ask'; });
      } else {
        await loadCorpus(true);
        status.innerHTML = `<p class="notice">${r.status === 'unchanged' ? 'Already indexed — nothing changed.' : `Added <strong>${esc(r.filename)}</strong> (${esc(r.investigation_id)}): ${esc(r.physical_pages)} pages, ${esc(r.chunks_added)} passages, ${esc(r.embedded_chunks)} with semantic search.`}</p>`;
      }
    } catch (err) { status.innerHTML = `<div class="error" role="alert">${esc(err.message)}</div>`; }
    button.disabled = false;
  });
  if (!visitor) renderPendingUploads();
}
async function renderPendingUploads() {
  const box = main.querySelector('#pending-uploads');
  if (!box) return;
  let pending = [];
  try { pending = (await api('/api/uploads/pending')).pending; } catch (err) { box.innerHTML = `<div class="error">${esc(err.message)}</div>`; return; }
  box.innerHTML = `<div class="section-head"><h2>Visitor uploads awaiting review</h2><span class="muted small">${pending.length} pending</span></div>` + (pending.length
    ? pending.map(p => `<div class="card row" style="gap:12px;align-items:center;flex-wrap:wrap"><div style="flex:1;min-width:220px"><strong>${esc(p.filename)}</strong><div class="muted small">${esc(p.pages)} pages · ${esc(p.passages)} passages · uploaded ${esc(p.uploaded_at)}</div></div>
        <input class="pend-inv" data-id="${esc(p.source_id)}" placeholder="Investigation ID, e.g. PSI-26" maxlength="79">
        <button class="btn primary" type="button" data-approve="${esc(p.source_id)}">Approve</button>
        <button class="btn" type="button" data-delete="${esc(p.source_id)}">Delete</button></div>`).join('')
    : '<p class="muted">No visitor uploads are waiting.</p>');
  box.querySelectorAll('[data-approve]').forEach(b => b.addEventListener('click', async () => {
    const investigation = box.querySelector(`.pend-inv[data-id="${b.dataset.approve}"]`).value.trim();
    if (!investigation) { toast('Enter an investigation ID to approve.'); return; }
    try { await postJSON('/api/uploads/approve', { source_id: b.dataset.approve, investigation }); toast('Approved and added to the shared collection.'); await loadCorpus(true); renderPendingUploads(); }
    catch (err) { toast(err.message); }
  }));
  box.querySelectorAll('[data-delete]').forEach(b => b.addEventListener('click', async () => {
    if (!confirm('Delete this upload and its index entries?')) return;
    try { await postJSON('/api/uploads/delete', { source_id: b.dataset.delete }); toast('Upload deleted.'); renderPendingUploads(); }
    catch (err) { toast(err.message); }
  }));
}

// ---------- start ----------
document.querySelector('.nav-toggle').addEventListener('click', e => {
  const nav = document.querySelector('#site-nav'), open = !nav.classList.contains('open');
  nav.classList.toggle('open', open); e.currentTarget.setAttribute('aria-expanded', String(open));
});
window.addEventListener('hashchange', () => { render(); if (!location.hash.includes('claim-')) main.focus({ preventScroll: true }); window.scrollTo(0, 0); });
async function start() {
  try { state.me = await api('/api/me'); } catch { state.me = { name: null, is_admin: false, mode: 'public' }; }
  const slot = document.querySelector('#ui-switch-slot'); if (slot) { slot.innerHTML = uiSwitchHTML(state.me, 'public'); bindUiSwitch(slot); }
  render();
  await Promise.all([loadCorpus(), loadCoverage()]);
  if (route() === 'home' || route() === 'sources') render();
}

// ---- Switch between the public UI and the review workspace ----
function uiSwitchHTML(me, current) {
  // Workspace mode: workspace at "/", public preview at "/public".
  // Public mode (Azure): public at "/", workspace at "/workspace" (admins only).
  if (!me || !me.is_admin) return '';
  const urls = me.mode === 'public' ? { public: '/', workspace: '/workspace' } : { public: '/public', workspace: '/' };
  const target = current === 'public' ? urls.workspace : urls.public;
  const on = current === 'workspace';
  return `<div class="ui-switch"><span class="ui-switch-label${on ? '' : ' active'}" aria-hidden="true">Public</span><button type="button" role="switch" aria-checked="${on}" aria-label="Review workspace view" data-ui-target="${target}" class="ui-switch-track"><span class="ui-switch-knob"></span></button><span class="ui-switch-label${on ? ' active' : ''}" aria-hidden="true">Workspace</span></div>`;
}
function bindUiSwitch(root) {
  root.querySelector('[data-ui-target]')?.addEventListener('click', e => { window.location.assign(e.currentTarget.dataset.uiTarget); });
}
// ---- Site-wide AI answer limit (public deployments) ----
state.limits = null;
async function loadLimits() {
  try { state.limits = await api('/api/limits'); } catch { state.limits = null; }
}
function limitsHint() {
  const l = state.limits;
  if (!l || !l.enabled || l.exempt) return '';
  if (l.remaining_today === 0) return ' AI answers for today are used up; keyword search still works.';
  const left = l.remaining_today != null ? ` ${l.remaining_today} AI answer${l.remaining_today === 1 ? '' : 's'} left today (site-wide).` : '';
  const wait = l.next_available_in_s ? ` Next one available in ${l.next_available_in_s} s.` : '';
  return left + wait;
}
loadLimits().then(() => { if (route() === 'ask') renderAsk(); });
start();
