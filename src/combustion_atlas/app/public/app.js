// Combustion Atlas public UI. Self-contained; talks only to this server's /api.
import { renderFlameStory, heroFlamesSVG } from './flame-story.js';
const main = document.querySelector('#main');
// The conversation survives a refresh (this tab only); finished turns only.
function loadChat() { try { return (JSON.parse(sessionStorage.getItem('atlas-chat') || '[]') || []).filter(t => !t.loading); } catch { return []; } }
function saveChat() { try { sessionStorage.setItem('atlas-chat', JSON.stringify(state.ask.turns.filter(t => !t.loading).slice(-12))); } catch { /* storage full or blocked */ } }
const state = {
  me: null, corpus: null, coverage: null, coverageError: '',
  ask: { draft: '', turns: loadChat(), loading: false, ai: localStorage.getItem('atlas-ai') !== 'off' },
  cov: { x: 'oxygen_pct', y: 'flow_cm_s', slots: [null, null, null], view: 'heatmap', grid: 'flex', facets: {}, cell: null, detail: null, initialized: false },
  land: { data: null, error: '', slots: [null, null, null], view: 'chart', selected: null, initialized: false },
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
// "Explore" is a menu of two pages: experiment coverage and the evidence landscape.
const isExplore = () => ['explore', 'coverage', 'landscape'].includes(route());
const isCoverage = () => ['explore', 'coverage'].includes(route());
const isLandscape = () => route() === 'landscape';
function exploreRoot(which) {
  const id = which === 'land' ? 'explore-land' : 'explore-cov';
  if (!main.querySelector(`#${id}`)) main.innerHTML = which === 'land' ? '<section id="explore-land" aria-labelledby="land-title"></section>' : '<div id="explore-cov"></div>';
  return main.querySelector(`#${id}`);
}
function renderExplore() { if (isLandscape()) renderLandscape(); else renderCoverage(); }
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
async function loadCorpus(force = false) {
  if (state.corpus && !force) return;
  try { state.corpus = await api('/api/corpus'); } catch { state.corpus = { documents: [], totals: {} }; }
}

// ---------- shell ----------
function renderShell() {
  const page = route();
  document.body.dataset.route = page; // lets a page restyle the backdrop (Ask has a photo)
  document.body.dataset.space = localStorage.getItem('atlas-space') === 'off' ? 'off' : 'on';
  document.querySelectorAll('[data-route]').forEach(a => { const current = a.dataset.route === page || (a.dataset.route === 'explore' && isExplore()) || (a.dataset.route === 'coverage' && page === 'explore');
    if (current) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
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
  const pages = { home: renderHome, ask: renderAsk, explore: renderExplore, coverage: renderExplore, landscape: renderExplore, sources: renderSources, upload: renderUpload };
  (pages[page] || renderHome)();
  document.title = `${{ home: 'Combustion Atlas', ask: 'Ask', explore: 'Experiment coverage', coverage: 'Experiment coverage', landscape: 'Evidence landscape', sources: 'Sources', upload: 'Add to corpus' }[page] || 'Combustion Atlas'} · Combustion Atlas`;
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
      <h1>Decades of NASA microgravity-combustion research, at your fingertips.</h1>
      <p class="lead">Combustion Atlas makes NASA's spacecraft fire-safety experiments searchable and comparable: every answer quotes the original report and page, and the coverage map shows where the evidence is thin.</p>
      <form class="hero-search" id="hero-search" role="search">
        <label for="hero-q" class="visually-hidden" hidden>Question</label>
        <input id="hero-q" type="search" maxlength="1000" placeholder="e.g. How does opposed-flow velocity affect flame spread?" aria-label="Ask a question">
        <button class="btn primary" type="submit">Ask</button>
      </form>
      <div class="chips hero-try" aria-label="Try asking"><span class="hint" style="margin:0">Try:</span>${HOME_TRY.map(q => `<button type="button" class="chip" data-try="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    </div>
    <button type="button" class="fs-hero" id="fs-hero" aria-label="Why fire is different in space: open the story">${heroFlamesSVG()}<span>Why fire is different in space ↓</span></button>
  </section>
  <section class="section fs-section" id="fire-story" aria-labelledby="fs-title"></section>
  <section class="section">
    <div class="grid cols-${state.me?.can_upload ? 4 : 3}">
      ${tile('#/ask', '?', 'Ask a question', 'Get answers built only from indexed NASA documents, with every claim linked to its page. Ask follow-ups in a chat.')}
      ${tile('#/coverage', '◎', 'Experiment coverage', 'See which conditions have been tested across investigations, and where this collection has no runs.')}
      ${tile('#/landscape', '⁘', 'Evidence landscape', 'A map of every indexed passage, figure and table, grouped into topics, with related evidence one click away.')}
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
    <p class="hint">Documents come from NASA's Physical Sciences Informatics repository and technical reports. Experiment runs come from NASA PSI experiment tables.</p>
  </section>`;
  main.querySelectorAll('[data-try]').forEach(b => b.addEventListener('click', () => askQuestion(b.dataset.try)));
  renderFlameStory(main.querySelector('#fire-story'), { onAsk: askQuestion });
  main.querySelector('#fs-hero').addEventListener('click', () => main.querySelector('#fire-story').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }));
  main.querySelector('#hero-search').addEventListener('submit', e => {
    e.preventDefault();
    const q = main.querySelector('#hero-q').value.trim();
    if (!q) return;
    askQuestion(q);
  });
}

// ---------- ask ----------
// Recommended questions, grouped by what they demonstrate. Each was checked against the
// indexed corpus.
const RECOMMENDED = [
  { group: 'Big picture', hint: 'General questions, answered across several reports', questions: [
    'How do flames behave in microgravity compared with on Earth?',
    'Why is fire safety on spacecraft different from fire safety on Earth?',
    'How does airflow affect whether a flame keeps burning in microgravity?',
  ] },
  { group: 'Answers from NASA reports', hint: 'Cited, quoted passages with page links', questions: [
    'Which variables were tested in BASS-II?',
    'How does opposed-flow velocity affect flame spread over thin PMMA?',
    'What did the Saffire experiments show about flame spread on large samples?',
  ] },
  { group: 'Figures', hint: 'AI descriptions of report figures, with the original page image', questions: [
    'Which components are labelled in Figure 5.1 of the BASS-II duct schematic?',
  ] },
];
const HOME_TRY = [
  'How does opposed-flow velocity affect flame spread over thin PMMA?',
  'What was the initial CO reading for BASS-II test O12?',
  'Which components are labelled in Figure 5.1 of the BASS-II duct schematic?',
  'What did the Saffire experiments show about flame spread on large samples?',
];
function recommendedHTML() {
  const chip = q => `<button type="button" class="chip" data-example="${esc(q)}">${esc(q)}</button>`;
  return `<details class="recommended" open><summary>Recommended questions</summary><div class="recommended-groups">${RECOMMENDED.map(g =>
    `<div class="recommended-group"><div class="recommended-title">${esc(g.group)}</div><div class="hint" style="margin:2px 0 8px">${esc(g.hint)}</div><div class="chips">${g.questions.map(chip).join('')}</div></div>`).join('')}</div></details>`;
}
function askQuestion(q) {
  if (route() !== 'ask') location.hash = '#/ask';
  setTimeout(() => sendQuestion(q), 0);
}
const SEND_ICON = '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function renderAsk() {
  const a = state.ask, turns = a.turns;
  const placeholder = turns.length ? 'Ask a follow-up or a new question…' : 'Ask about materials, conditions, results or methods…';
  main.innerHTML = `<div class="chat">
    <div class="chat-head"><div><div class="eyebrow">Ask</div><h1>Ask the evidence</h1></div><span class="spacer"></span>${turns.length ? '<button type="button" class="btn small" id="new-chat">New chat</button>' : ''}</div>
    <div class="chat-thread" id="chat-thread" aria-live="polite">${turns.length ? turns.map(turnHTML).join('') : `
      <p class="chat-intro">Answers are built only from indexed NASA documents and quote them verbatim. Ask follow-up questions and the conversation carries over.</p>
      ${recommendedHTML()}`}</div>
    <form class="chat-composer" id="ask-form">
      <div class="composer-box"><label for="q" class="visually-hidden">Question</label>
        <textarea id="q" rows="1" maxlength="1000" placeholder="${placeholder}">${esc(a.draft)}</textarea>
        <button class="send" type="submit" aria-label="Send" ${a.loading ? 'disabled' : ''}>${SEND_ICON}</button></div>
      <div class="composer-meta">
        <span class="ui-switch"><button type="button" class="ui-switch-track" id="ai-toggle" role="switch" aria-checked="${a.ai}" aria-label="AI answers"><span class="ui-switch-knob"></span></button><span class="ui-switch-label${a.ai ? ' active' : ''}">AI ${a.ai ? 'on' : 'off'}</span></span>
        <span class="hint" style="margin:0">${a.ai ? `Cited answers from the indexed documents.${limitsHint()}` : 'Keyword search only: no AI calls.'}</span>
        <span class="spacer"></span>
        <span class="ui-switch"><button type="button" class="ui-switch-track" id="space-toggle" role="switch" aria-checked="${document.body.dataset.space !== 'off'}" aria-label="Space background"><span class="ui-switch-knob"></span></button><span class="ui-switch-label${document.body.dataset.space !== 'off' ? ' active' : ''}">Space background</span></span>
      </div>
      <p class="photo-credit">Background: orbital sunrise over the Pacific Ocean, photographed from the International Space Station on Aug. 6, 2024. Image: NASA (iss071e439624).</p>
    </form></div>`;
  const q = main.querySelector('#q');
  const grow = () => { q.style.height = 'auto'; q.style.height = `${Math.min(q.scrollHeight, 200)}px`; };
  grow();
  q.addEventListener('input', () => { a.draft = q.value; grow(); });
  q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); main.querySelector('#ask-form').requestSubmit(); } });
  main.querySelector('#ask-form').addEventListener('submit', e => { e.preventDefault(); const text = q.value.trim(); if (text) sendQuestion(text); });
  main.querySelector('#space-toggle').addEventListener('click', () => {
    const on = document.body.dataset.space === 'off';
    localStorage.setItem('atlas-space', on ? 'on' : 'off');
    document.body.dataset.space = on ? 'on' : 'off';
    renderAsk();
    main.querySelector('#space-toggle')?.focus();
  });
  main.querySelector('#ai-toggle').addEventListener('click', () => { if (a.loading) return; a.ai = !a.ai; localStorage.setItem('atlas-ai', a.ai ? 'on' : 'off'); renderAsk(); });
  main.querySelector('#new-chat')?.addEventListener('click', () => { if (a.loading) return; a.turns = []; a.draft = ''; saveChat(); renderAsk(); main.querySelector('#q').focus(); });
  main.querySelectorAll('[data-example]').forEach(b => b.addEventListener('click', () => sendQuestion(b.dataset.example)));
}
function turnHTML(t) {
  return `<article class="turn" id="turn-${t.id}">
    <div class="msg user"><div class="bubble">${esc(t.question)}</div></div>
    <div class="msg bot"><img class="avatar" src="/p/logo.svg" alt="" width="28" height="28"><div class="turn-body">${turnBodyHTML(t)}</div></div>
  </article>`;
}
function rerenderTurn(t) {
  const el = main.querySelector(`#turn-${t.id} .turn-body`);
  if (el && route() === 'ask') el.innerHTML = turnBodyHTML(t);
}
const scrollToTurn = t => main.querySelector(`#turn-${t.id}`)?.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
// Earlier answered turns, compacted, so follow-ups ("what about FLEX?") can be understood.
function historyFor(turn) {
  return state.ask.turns.filter(t => t !== turn && t.result && !t.error).slice(-3)
    .map(t => ({ question: t.question.slice(0, 1000), answer: (t.result.answer?.claims || []).map(c => c.text).join(' ').slice(0, 4000) }));
}
async function sendQuestion(question) {
  const a = state.ask;
  if (!question || a.loading) return;
  const turn = { id: Date.now().toString(36), question, ai: a.ai, loading: true, progress: [], result: null, error: '' };
  const history = historyFor(turn);
  a.turns.push(turn); a.loading = true; a.draft = '';
  if (route() === 'ask') { renderAsk(); scrollToTurn(turn); }
  try {
    turn.result = { kind: 'answer', ...(await streamAnswer(turn, history)) };
  } catch (e) { turn.error = e.message; }
  turn.loading = false; a.loading = false;
  saveChat();
  await loadLimits();
  if (route() === 'ask') { renderAsk(); scrollToTurn(turn); main.querySelector('#q')?.focus({ preventScroll: true }); }
}
// Streams NDJSON progress from /api/ask/stream; falls back to /api/ask when the route is absent.
async function streamAnswer(turn, history = []) {
  // AI off: keyword search only, no provider calls of any kind.
  const include_sources = myUploads().map(u => u.source_id);
  const body = turn.ai
    ? { question: turn.question, history, method: 'hybrid', generate_answer: true, allow_provider_calls: true, include_sources }
    : { question: turn.question, history, method: 'keyword', generate_answer: false, allow_provider_calls: false, include_sources };
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
    if (event.type === 'progress') { turn.progress.push(event); rerenderTurn(turn); }
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
  if (!result) throw new Error('The connection closed before the answer arrived. Please try again.');
  return result;
}
// ---- Progress as a fire: search steps add logs, writing the answer ignites it ----
const FUEL_STAGES = new Set(['keyword', 'embedding', 'semantic', 'ranking', 'records', 'figures', 'retrieved', 'context']);
const STEP_ICON = {
  log: '<svg viewBox="0 0 20 12" width="20" height="12" aria-hidden="true"><rect x="1" y="2" width="15" height="8" rx="4" fill="#9a6232"/><ellipse cx="16" cy="6" rx="3" ry="4" fill="#d9a066"/><ellipse cx="16" cy="6" rx="1.4" ry="2" fill="none" stroke="#9a6232" stroke-width=".8"/></svg>',
  flame: '<svg viewBox="0 0 12 16" width="12" height="16" aria-hidden="true"><path d="M6 1c1 3 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 1.5.8 2.5 1.8 2.5C4 6 5 3 6 1z" fill="#ef6a2a"/><path d="M6 8c.6 1.4 2.2 2.2 2.2 4a2.2 2.2 0 0 1-4.4 0c0-1 .6-1.7 1.1-2.2C5 9 5.6 8.7 6 8z" fill="#ffc94a"/></svg>',
  check: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M10.4 10.4 14 14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  dot: '<svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3" fill="currentColor"/></svg>',
};
function stepIcon(stage) {
  if (FUEL_STAGES.has(stage)) return STEP_ICON.log;                       // search adds fuel
  if (['generating', 'retrying', 'fallback', 'answer'].includes(stage)) return STEP_ICON.flame; // writing burns it
  if (['checking', 'repairing', 'filtering'].includes(stage)) return STEP_ICON.check;            // fact checks
  return STEP_ICON.dot;
}
const stepHTML = (s, cls) => `<li class="${cls}"><span class="step-icon">${stepIcon(s.stage)}</span><span class="step-text">${esc(s.message)}</span><span class="muted small">${fmt(s.elapsed_s, 3)} s</span></li>`;
function progressHTML(t) {
  const steps = t.progress;
  const logs = steps.filter(s => FUEL_STAGES.has(s.stage)).length;
  const lit = steps.some(s => ['generating', 'retrying', 'fallback', 'answer'].includes(s.stage));
  const title = lit ? 'Burning…' : logs ? 'Adding logs to the fire…' : 'Striking a match…';
  return `<section class="card burn-card" aria-label="Progress"><div class="row"><span class="burn-flame${lit ? ' lit' : ''}" style="--fuel:${Math.min(logs, 6)}" aria-hidden="true"><img src="/p/logo.svg" alt="" width="28" height="28"></span><h3 style="margin:0" aria-live="polite">${title}</h3><span class="burn-logs" aria-label="${logs} search steps">${STEP_ICON.log.repeat(Math.min(logs, 6))}</span><span class="spacer"></span><span class="muted small">${steps.length ? `${fmt(steps[steps.length - 1].elapsed_s, 3)} s` : ''}</span></div>
    <ol class="steps fire-steps">${steps.length ? steps.map((s, i) => stepHTML(s, i === steps.length - 1 ? 'current' : 'done')).join('') : `<li class="current"><span class="step-icon">${STEP_ICON.dot}</span><span class="step-text">Starting…</span></li>`}</ol></section>`;
}
// After the answer arrives, keep the steps as a collapsed summary above it.
function stepsSummaryHTML(steps, failed = false) { // steps of one turn
  if (!steps?.length) return '';
  const total = fmt(steps[steps.length - 1].elapsed_s, 3);
  const label = failed ? `Fizzled out after ${total} s` : `Burned in ${total} s`;
  const icon = failed ? '⚠' : `<img src="/p/logo.svg" alt="" width="18" height="18" class="burn-done">`;
  return `<details class="card steps-summary"><summary><span class="row" style="gap:8px">${icon}<span>${esc(label)}</span></span><span class="muted small">${steps.length} step${steps.length === 1 ? '' : 's'}</span></summary>
    <ol class="steps fire-steps">${steps.map(s => stepHTML(s, 'done')).join('')}</ol></details>`;
}
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
  const visual = src.visual ? ` · <span class="pill warn">${esc(src.visual.kind)} ${esc(src.visual.label)} · AI description</span>` : '';
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
function sourcesSummary(allResults, fold = false) {
  if (!allResults?.length) return '';
  const tableData = tableDataSection(allResults);
  const results = allResults.filter(r => !(r.record_card && (r.record_card.kind === 'row' || r.record_card.kind === 'table')));
  if (!results.length) return tableData;
  const docs = new Set(results.map(r => r.source_id));
  const head = `<h3>Sources searched</h3><span class="muted small">${results.length} passages · ${docs.size} document${docs.size === 1 ? '' : 's'}</span>`;
  return tableData + `<${fold ? 'details' : 'section'} class="card sources-card">${fold ? `<summary class="section-head">${head}</summary>` : `<div class="section-head">${head}</div>`}
    <ul class="source-list">${results.map(r => `<li><div class="row"><strong>${esc(r.filename)}</strong>${r.record_card ? `<span class="pill ok">Table record · ${esc(r.record_card.review_action)}</span>` : `<span class="pill">page ${esc(r.physical_page)}</span>`}${r.visual ? `<span class="pill warn">${esc(r.visual.kind)} ${esc(r.visual.label)} · AI description</span>` : ''}${r.investigation_id ? `<span class="pill">${esc(invName(r.investigation_id))}</span>` : ''}<span class="spacer"></span>${r.record_card ? `<span class="small muted">${esc(r.record_card.locator || '')}</span>` : `<a class="small" href="${docLink(r.source_id, r.physical_page)}" target="_blank" rel="noopener noreferrer">Open page ↗</a>`}</div>
      <div class="muted small">${esc(String(r.visual ? r.visual.caption : r.text || '').replace(/\s+/g, ' ').slice(0, 220))}…</div>${r.visual && String(r.crop_url || '').startsWith('/api/visuals/') ? `<img class="crop result-thumb" loading="lazy" src="${esc(r.crop_url)}" alt="Original page image for ${esc(r.visual.kind)} ${esc(r.visual.label)}">` : ''}</li>`).join('')}</ul></${fold ? 'details' : 'section'}>`;
}
function turnBodyHTML(t) {
  if (t.loading) return progressHTML(t);
  if (t.error) return stepsSummaryHTML(t.progress, true) + `<div class="error" role="alert">${esc(t.error)}</div>`;
  if (!t.result) return '';
  if (t.progress.length) return stepsSummaryHTML(t.progress) + askResultBody(t);
  return askResultBody(t);
}
function askResultBody(t) {
  const a = t;
  const results = a.result.results || [];
  const byId = Object.fromEntries(results.map(r => [r.chunk_id, r]));
  {
    const ans = a.result.answer;
    const notices = [
      a.result.limited ? `<strong>AI answers are paused.</strong> ${esc(a.result.limited.reason)} Showing keyword search results below.` : '',
      a.result.answer_unavailable ? `<strong>No AI answer this time.</strong> ${esc(a.result.answer_unavailable)}` : '',
      a.result.retrieval_fallback ? esc(a.result.retrieval_fallback) : '',
      a.result.answered_by?.backup ? `Answered by the backup model ${esc(a.result.answered_by.model)} (${esc(a.result.answered_by.provider)}) because the main model was unavailable. The same quote and number checks applied.` : '',
      !ans && !a.result.limited && !a.result.answer_unavailable ? '<strong>AI answers are off.</strong> Showing keyword search results: reviewed table data first, then document passages.' : '',
    ].filter(Boolean);
    const limited = notices.length ? `<section class="card notice" role="status">${notices.join('<br>')}</section>` : '';
    if (!ans) return limited + sourcesSummary(results);
    const partial = ans.status === 'answered' && (ans.limitations || []).length > 0;
    const status = ans.status !== 'answered' ? '<span class="pill bad">Insufficient evidence</span>' : partial ? '<span class="pill warn">Partial evidence</span>' : '<span class="pill ok">Answered from sources</span>';
    const body = ans.status !== 'answered'
      ? `<p>The indexed documents do not contain an answer to this question.</p>`
      : ans.claims.map(c => claimHTML(c, byId)).join('');
    return `<section class="card stack"><div class="row"><h2 style="margin:0">Answer</h2>${status}</div>${body}
      ${(ans.limitations || []).map(l => `<p class="notice">${esc(l)}</p>`).join('')}
      </section>${sourcesSummary(results, true)}`;
  }
}

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
  if (!state.coverage && !state.coverageError) { exploreRoot('cov').innerHTML = '<p class="loading">Loading experiment coverage…</p>'; loadCoverage().then(() => isCoverage() && renderCoverage()); return; }
  const head = pageHead('Explore', 'Experiment coverage', 'Where have experiments actually been run? Each heatmap cell counts the runs whose test conditions fall in that range. Empty cells are conditions with no runs in this collection.');
  if (state.coverageError) { exploreRoot('cov').innerHTML = head + emptyBox('Not available yet', state.coverageError); return; }
  initCoverageSelection();
  const cov = state.coverage, c = state.cov;
  // The heatmap is the only coverage view; the points and table views are not shown.
  const viewSwitch = '';
  c.view = 'heatmap';
  if (c.view === 'heatmap' && (cov.grids || []).length) { renderHeatmapPage(head, viewSwitch); return; }
  const fields = (cov.fields || []).filter(f => f.count > 0);
  const fieldOpt = sel => fields.map(f => `<option value="${esc(f.key)}" ${sel === f.key ? 'selected' : ''}>${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''} · ${count(f.count)}</option>`).join('');
  const reviewed = cov.records.filter(r => r.review_status === 'reviewed').length;
  const famChips = (cov.families || []).map(f => {
    const slot = slotOf(f.key);
    const sw = slot >= 0 ? legendShape(SHAPES[slot], `var(--s${slot + 1})`) : legendShape('circle', 'var(--neutral)');
    return `<button type="button" class="chip" data-family="${esc(f.key)}" aria-pressed="${slot >= 0}">${sw}${esc(f.label)} <span class="muted">${count(f.count)}</span></button>`;
  }).join('');
  exploreRoot('cov').innerHTML = head + `
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
const extLink = (url, text) => url ? `<a href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${esc(text)} ↗</a>` : esc(text);
const runSource = r => `${extLink(r.source?.url, `NASA ${r.investigation_id}`)}<br><span class="muted">${esc(r.source?.file || '')}${r.source?.record != null ? `, record ${esc(r.source.record)}` : ''}</span>`;
const plannedSource = p => `${p.document_id ? `<a href="${docLink(p.document_id, p.page)}" target="_blank" rel="noopener noreferrer">EIRD Table ${esc(p.table)}, page ${esc(p.page)} ↗</a>` : `EIRD Table ${esc(p.table)}, page ${esc(p.page)}`}${p.source_url ? `<br>${extLink(p.source_url, `NASA ${p.investigation_id}`)}` : ''}`;
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
  exploreRoot('cov').innerHTML = head + `
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
    ${runs.map(r => `<tr data-row="${esc(r.id)}" tabindex="0" style="cursor:pointer"><td>${esc(r.test_id)}${r.review_status === 'reviewed' ? ' <span class="pill ok">Reviewed</span>' : ''}</td><td>${esc(invName(r.investigation_id))}</td>${cols.map(([, f, n]) => `<td${n ? ' class="num"' : ''}>${esc(f(r) || '—')}</td>`).join('')}<td class="small">${runSource(r)}</td></tr>`).join('')}
  </tbody></table></div>` : `<p class="muted">No runs in this collection fall in ${gap ? 'this range' : 'this cell'}.</p>`;
  const proposed = cell.planned_ids.map(i => state.coverage.proposed?.[i]).filter(Boolean);
  const plannedTable = proposed.length ? `<h4 style="margin:20px 0 8px">Planned tests · ${count(proposed.length)}</h4><p class="muted small" style="margin:0 0 8px">From the FLEX EIRD test matrices: planned conditions, not runs, with no results.</p>
    <div class="table-scroll" style="max-height:300px"><table><thead><tr><th>Test</th><th>Source</th><th>Fuel</th><th>Added diluent</th><th class="num">O₂ (%)</th><th class="num">Pressure (atm)</th></tr></thead><tbody>
    ${proposed.map(p => `<tr><td>${esc(p.test_id)}</td><td class="small">${plannedSource(p)}</td><td>${esc(({ C7H16: 'Heptane (C₇H₁₆)', CH3OH: 'Methanol (CH₃OH)' })[p.fuel] || p.fuel || '—')}</td><td>${esc(p.suppressant || 'none')}</td><td class="num">${fmt(p.fields?.oxygen_pct)}</td><td class="num">${p.fields?.pressure_kpa != null ? fmt(p.fields.pressure_kpa / 101.325) : '—'}</td></tr>`).join('')}
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
    ${records.map(r => `<tr data-row="${esc(r.id)}" tabindex="0" style="cursor:pointer"><td>${esc(familyLabel(r.family))}</td><td>${esc(r.test_id)}</td><td>${esc(r.material || '—')}</td>${cols.map(f => `<td class="num">${fmt(r[f.key])}</td>`).join('')}<td>${esc(r.gravity || '—')}</td><td>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : ''}</td><td class="small">${runSource(r)}</td></tr>`).join('')}
  </tbody></table></div>`;
}
function bindRows(el) { el.querySelectorAll('[data-row]').forEach(tr => { const open = e => { if (e.target.closest('a')) return; state.cov.detail = tr.dataset.row; renderCoverageDetail(); }; tr.addEventListener('click', open); tr.addEventListener('keydown', e => { if (e.key === 'Enter') open(e); }); }); }
function renderCoverageDetail() {
  const el = main.querySelector('#cov-detail'); if (!el) return;
  const r = state.coverage.records.find(x => String(x.id) === String(state.cov.detail));
  if (!r) { el.innerHTML = ''; return; }
  const row = (k, v) => v == null || v === '' ? '' : `<dt>${esc(k)}</dt><dd>${v}</dd>`;
  const outcomes = Object.entries(r.outcomes || {});
  el.innerHTML = `<section class="card"><div class="row"><h3 style="margin:0">${esc(familyLabel(r.family))} · ${esc(r.test_id)}</h3>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : ''}<span class="spacer"></span><button class="btn small" type="button" id="close-detail">Close</button></div>
    <dl class="kv" style="margin-top:16px">${row('Investigation', esc(invName(r.investigation_id)))}${row('Material', esc(r.material))}${row('Geometry', esc(r.geometry))}${row('Oxygen', r.oxygen_pct != null ? `${fmt(r.oxygen_pct)} %` : null)}${row('Flow', r.flow_cm_s != null ? `${fmt(r.flow_cm_s)} cm/s` : null)}${row('Pressure', r.pressure_kpa != null ? `${fmt(r.pressure_kpa)} kPa` : null)}${row('Gravity', esc(r.gravity))}
    ${outcomes.map(([k, o]) => row(k.replaceAll('_', ' '), `${o.value != null ? fmt(o.value) : '—'}${o.unit ? ` ${esc(o.unit)}` : ''} <span class="muted small">(source text: “${esc(o.raw)}”)</span>`)).join('')}
    ${row('Source', runSource(r))}</dl></section>`;
  el.querySelector('#close-detail').addEventListener('click', () => { state.cov.detail = null; renderCoverageDetail(); });
}

// ---------- evidence landscape ----------
const KIND_SHAPE = { passage: 'circle', figure: 'square', table: 'triangle' };
const KIND_LABEL = { passage: 'Text passage', figure: 'Figure description', table: 'Reviewed table' };
async function loadLandscape() {
  if (state.land.data || state.land.error) return;
  try {
    const d = await api('/api/landscape');
    if (d.missing || !d.points?.length) state.land.error = 'The evidence landscape has not been built for this collection yet.';
    else { d.byId = Object.fromEntries(d.points.map(p => [p.id, p])); d.byCluster = Object.fromEntries(d.clusters.map(c => [c.id, c])); state.land.data = d; }
  } catch (e) { state.land.error = e.message; }
}
const landSlot = id => state.land.slots.indexOf(id);
const topicName = id => state.land.data?.byCluster[id]?.label || 'No topic';
function renderLandscape() {
  const L = state.land, root = exploreRoot('land');
  const head = pageHead('Explore', '<span id="land-title">Evidence landscape</span>', 'Every indexed passage, figure description and reviewed table, placed so that passages with similar meaning sit close together. Topics are found automatically. Use it to see what the collection covers and to jump between related evidence.');
  if (!L.data && !L.error) { root.innerHTML = head + '<p class="loading">Loading the evidence landscape…</p>'; loadLandscape().then(() => isLandscape() && renderLandscape()); return; }
  if (L.error) { root.innerHTML = head + emptyBox('Not available yet', L.error); return; }
  const d = L.data;
  if (!L.initialized) { // start with the three largest topics highlighted
    if (/[?&]view=3d\b/.test(location.hash)) L.view = 'three';
    [...d.clusters].sort((a, b) => b.size - a.size).slice(0, 3).forEach((c, i) => { L.slots[i] = c.id; });
    L.initialized = true;
  }
  const options = [...d.clusters].sort((a, b) => b.size - a.size).map(c => `<label class="topic-opt" title="${esc(c.description || c.keywords.join(', '))}"><input type="checkbox" data-topic="${c.id}"><span class="topic-sw" data-sw="${c.id}"></span><span class="topic-name">${esc(c.label)}</span><span class="muted small">${count(c.size)}</span></label>`).join('');
  root.innerHTML = head + `
  <div class="row" style="margin-bottom:16px">${d.stale ? '<span class="pill warn">Documents changed since this map was built; new ones are not shown yet</span>' : ''}<span class="muted small">${count(d.points.length)} items · ${count(d.clusters.length)} topics · ${count(d.noise)} without a clear topic</span></div>
  <section class="card">
    <div class="controls">
      <details class="topic-menu"${L.menuOpen ? ' open' : ''}>
        <summary class="btn small"><span>Topics</span> <span class="muted" data-land-count></span> <span aria-hidden="true">▾</span></summary>
        <div class="topic-menu-panel">
          <div class="row topic-menu-head"><span class="small muted">Highlight up to three topics</span><span class="spacer"></span><button type="button" class="linklike" data-land-clear>Clear</button></div>
          <div class="topic-menu-list" role="group" aria-label="Topics to highlight (up to three)">${options}</div>
        </div>
      </details>
      <div class="legend land-selected" data-land-selected aria-label="Highlighted topics"></div>
      <span class="spacer"></span>
      <button type="button" class="btn small" data-land-table aria-pressed="${L.view === 'table'}">${L.view === 'table' ? 'Show map' : 'Topic list'}</button>
    </div>
    <div id="land-view" style="margin-top:16px"></div>
  </section>
  <div id="land-detail" class="section" aria-live="polite"></div>
  <details class="section small muted"><summary>How this map is made</summary><ul class="plain">${(d.notes || []).map(n => `<li>${esc(n)}</li>`).join('')}<li>Method: ${esc(d.params?.projection)}; ${esc(d.params?.clustering)}; related evidence by ${esc(d.params?.neighbors)}. Nearby points have similar meaning.</li>${d.generated_at ? `<li>Built ${esc(d.generated_at.slice(0, 10))}.</li>` : ''}</ul></details>`;
  const menu = root.querySelector('.topic-menu');
  menu.addEventListener('toggle', () => { L.menuOpen = menu.open; });
  root.querySelectorAll('[data-topic]').forEach(b => b.addEventListener('change', () => toggleTopic(Number(b.dataset.topic))));
  root.querySelector('[data-land-clear]').addEventListener('click', () => { L.slots = [null, null, null]; refreshLandscape(); });
  root.querySelector('[data-land-table]').addEventListener('click', e => {
    if (L.view === 'table') L.view = L.lastMap || 'chart'; else { L.lastMap = L.view; L.view = 'table'; }
    e.currentTarget.textContent = L.view === 'table' ? 'Show map' : 'Topic list'; e.currentTarget.setAttribute('aria-pressed', String(L.view === 'table'));
    drawLandscapeView();
  });
  if (!renderLandscape.bound) { // close the dropdown on outside click or Escape
    renderLandscape.bound = true;
    document.addEventListener('click', e => { const m = main.querySelector('.topic-menu[open]'); if (m && !m.contains(e.target)) { m.open = false; } });
    document.addEventListener('keydown', e => { const m = main.querySelector('.topic-menu[open]'); if (e.key === 'Escape' && m) { m.open = false; m.querySelector('summary').focus(); } });
  }
  syncTopicMenu();
  drawLandscapeView();
  renderLandscapeDetail();
}
// Update checkboxes, swatches and the selected-topic legend in place (keeps the menu open).
function syncTopicMenu() {
  const L = state.land, root = main.querySelector('#explore-land'); if (!root) return;
  const full = !L.slots.includes(null);
  root.querySelectorAll('[data-topic]').forEach(b => {
    const id = Number(b.dataset.topic), slot = landSlot(id);
    b.checked = slot >= 0; b.disabled = full && slot < 0;
    b.closest('label').classList.toggle('disabled', b.disabled);
    root.querySelector(`[data-sw="${id}"]`).innerHTML = legendShape('circle', slot >= 0 ? `var(--s${slot + 1})` : 'var(--neutral)');
  });
  const n = L.slots.filter(x => x !== null).length;
  root.querySelector('[data-land-count]').textContent = `${n} of 3 highlighted`;
  root.querySelector('[data-land-selected]').innerHTML = L.slots.map((id, i) => id !== null ? `<span>${legendShape('circle', `var(--s${i + 1})`)}${esc(topicName(id))}</span>` : '').join('');
}
function refreshLandscape() { syncTopicMenu(); drawLandscapeView(); renderLandscapeDetail(); }
function toggleTopic(id) {
  const L = state.land, slot = landSlot(id);
  if (slot >= 0) L.slots[slot] = null; // freeing a slot never repaints the others
  else { const free = L.slots.indexOf(null); if (free < 0) { syncTopicMenu(); return; } L.slots[free] = id; L.flyTo = id; }
  refreshLandscape();
}
function drawLandscapeView() {
  const el = main.querySelector('#land-view'); if (!el) return;
  const L = state.land, d = L.data;
  if (L.raf) { cancelAnimationFrame(L.raf); L.raf = 0; }
  if (L.view === 'three') { drawLandscape3D(el); bindDimSwitch(el); return; }
  if (L.view === 'table') {
    el.innerHTML = `<div class="table-scroll"><table><thead><tr><th>Topic</th><th>What it covers</th><th class="num">Items</th><th>Main investigations</th><th>Keywords</th></tr></thead><tbody>
      ${[...d.clusters].sort((a, b) => b.size - a.size).map(c => `<tr data-trow="${c.id}" tabindex="0" style="cursor:pointer"${landSlot(c.id) >= 0 ? ' aria-selected="true"' : ''}><td><strong>${esc(c.label)}</strong></td><td class="small">${esc(c.description || '')}</td><td class="num">${count(c.size)}</td><td class="small">${Object.entries(c.investigations).slice(0, 3).map(([k, n]) => `${esc(invName(k))} ${count(n)}`).join(' · ')}</td><td class="small muted">${esc(c.keywords.slice(0, 5).join(', '))}</td></tr>`).join('')}
    </tbody></table></div><p class="hint">Click a topic to highlight it on the map.</p>`;
    el.querySelectorAll('[data-trow]').forEach(tr => { const go = () => { toggleTopic(Number(tr.dataset.trow)); }; tr.addEventListener('click', go); tr.addEventListener('keydown', e => { if (e.key === 'Enter') go(); }); });
    return;
  }
  const W = 880, H = 620, pad = 18;
  const sx = v => pad + v * (W - 2 * pad), sy = v => pad + (1 - v) * (H - 2 * pad);
  const sel = L.selected ? d.byId[L.selected] : null;
  const active = L.slots.some(s => s !== null);
  const order = [...d.points].sort((a, b) => (landSlot(a.cluster) >= 0) - (landSlot(b.cluster) >= 0));
  const marks = order.map(p => {
    const slot = p.cluster >= 0 ? landSlot(p.cluster) : -1, x = sx(p.x), y = sy(p.y);
    const fill = slot >= 0 ? `var(--s${slot + 1})` : 'var(--neutral)';
    const cls = `pt land${slot < 0 && active ? ' dim' : ''}${p.id === L.selected ? ' selected' : ''}`;
    return `<g class="hit" tabindex="-1" data-pid="${esc(p.id)}">${shapeSVG(KIND_SHAPE[p.kind] || 'circle', x, y, slot >= 0 ? 4.5 : 3.5, cls, fill)}</g>`;
  }).join('');
  const links = sel ? sel.neighbors.map(id => d.byId[id]).filter(Boolean).map(n => `<line class="knn" x1="${sx(sel.x).toFixed(1)}" y1="${sy(sel.y).toFixed(1)}" x2="${sx(n.x).toFixed(1)}" y2="${sy(n.y).toFixed(1)}"/>`).join('') : '';
  // Direct labels: highlighted topics, else the largest topics.
  const labelled = active ? d.clusters.filter(c => landSlot(c.id) >= 0) : [...d.clusters].sort((a, b) => b.size - a.size).slice(0, 8);
  const labels = labelled.map(c => { const x = sx(c.x), y = sy(c.y); const anchor = x > W * 0.8 ? 'end' : x < W * 0.2 ? 'start' : 'middle'; return `<text class="land-label${active ? ' strong' : ''}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}">${esc(c.label)}</text>`; }).join('');
  const legend = L.slots.map((id, i) => id !== null ? `<span>${legendShape('circle', `var(--s${i + 1})`)}${esc(topicName(id))}</span>` : '').join('')
    + `<span>${legendShape('circle', 'var(--neutral)')}${active ? 'Other topics' : 'All items'}</span>`
    + Object.entries(KIND_SHAPE).map(([k, sh]) => `<span>${legendShape(sh, 'var(--ink-2)')}${KIND_LABEL[k]}</span>`).join('')
    + (sel ? '<span><svg width="22" height="14" aria-hidden="true"><line class="knn" x1="1" y1="7" x2="21" y2="7"/></svg>Link to related evidence</span>' : '');
  el.innerHTML = `<div class="chart-wrap">${dimSwitchHTML()}<svg class="chart land-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Map of ${d.points.length} indexed items in ${d.clusters.length} topics. The topic list view gives the same information as a table.`)}">${links}${marks}${labels}</svg><div class="tooltip" id="land-tip" hidden></div></div>
    <div class="legend" aria-label="Legend">${legend}</div>
    <p class="hint">Hover to preview, click an item for its source and related evidence. Position reflects meaning of the text, not test conditions.</p>`;
  const tip = el.querySelector('#land-tip'), svg = el.querySelector('svg');
  // One delegated listener set instead of 1,460.
  const itemAt = ev => ev.target.closest?.('[data-pid]');
  svg.addEventListener('mousemove', ev => {
    const g = itemAt(ev); if (!g) { tip.hidden = true; return; }
    const p = d.byId[g.dataset.pid], box = svg.getBoundingClientRect();
    tip.innerHTML = `<strong>${esc(p.label || KIND_LABEL[p.kind])}</strong> · ${esc(p.filename)}${p.page ? `, p. ${esc(p.page)}` : ''}<br><span class="muted">${esc(p.investigation ? invName(p.investigation) : '')}${p.cluster >= 0 ? ` · ${esc(topicName(p.cluster))}` : ''}</span><br>${esc(p.snippet.slice(0, 160))}${p.snippet.length > 160 ? '…' : ''}`;
    tip.hidden = false;
    const px = ev.clientX - box.left, py = ev.clientY - box.top;
    tip.style.left = `${Math.max(0, Math.min(px + 14, box.width - 300))}px`; tip.style.top = `${Math.min(py + 14, box.height - 120)}px`;
  });
  svg.addEventListener('mouseleave', () => { tip.hidden = true; });
  svg.addEventListener('click', ev => { const g = itemAt(ev); if (g) selectLandItem(g.dataset.pid); });
  bindDimSwitch(el);
}
// ---------- evidence landscape: 3-D view (canvas, no libraries) ----------
// Home view: centred on the middle of the cloud's bounding box, so outlying topics stay in frame.
function landHome() {
  const pts = state.land.data.points, lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const p of pts) for (let i = 0; i < 3; i++) { lo[i] = Math.min(lo[i], p.p3[i]); hi[i] = Math.max(hi[i], p.p3[i]); }
  const radius = Math.max(...hi.map((v, i) => v - lo[i])) / 2 || 1;
  return { yaw: 0.6, pitch: 0.35, zoom: 1.15 / radius, target: lo.map((v, i) => (v + hi[i]) / 2) };
}
const CAM_HOME = () => landHome();
function drawLandscape3D(el) {
  const L = state.land, d = L.data;
  L.cam = L.cam || CAM_HOME();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (L.spin === undefined) L.spin = !reduced;
  const active = L.slots.some(s => s !== null);
  el.innerHTML = `<div class="chart-wrap land3d-wrap">${dimSwitchHTML()}<canvas class="land3d" tabindex="0" role="img" aria-label="${esc(`Rotatable 3-D map of ${d.points.length} indexed items in ${d.clusters.length} topics. Use the topic list view for the same information as a table.`)}"></canvas><div class="tooltip" id="land-tip" hidden></div>
      <div class="land3d-tools"><button type="button" class="btn small" id="land-spin">${L.spin ? 'Pause spin' : 'Spin'}</button><button type="button" class="btn small" id="land-reset">Reset view</button></div></div>
    <div class="legend" aria-label="Legend">${L.slots.map((id, i) => id !== null ? `<span>${legendShape('circle', `var(--s${i + 1})`)}${esc(topicName(id))}</span>` : '').join('')}<span>${legendShape('circle', 'var(--neutral)')}${active ? 'Other topics' : 'All items'}</span>${Object.entries(KIND_SHAPE).map(([k, sh]) => `<span>${legendShape(sh, 'var(--ink-2)')}${KIND_LABEL[k]}</span>`).join('')}</div>
    <p class="hint">Drag to spin · scroll or pinch to zoom · click a point for details · click a topic above to fly to it · double-click to reset. Arrow keys and +/− work too.</p>`;
  const canvas = el.querySelector('canvas'), tip = el.querySelector('#land-tip'), ctx = canvas.getContext('2d');
  const css = getComputedStyle(document.body), cv = n => css.getPropertyValue(n).trim();
  const colors = { s: [cv('--s1'), cv('--s2'), cv('--s3')], neutral: cv('--neutral'), ink: cv('--ink'), ink2: cv('--ink-2'), surface: cv('--surface') };
  let W = 0, H = 0, projected = [], dirty = true;
  const resize = () => {
    const dpr = window.devicePixelRatio || 1; W = canvas.clientWidth; H = Math.min(680, Math.max(420, Math.round(W * 0.68)));
    canvas.style.height = `${H}px`; canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); dirty = true;
  };
  const project = (p3) => {
    const c = L.cam, x0 = p3[0] - c.target[0], y0 = p3[1] - c.target[1], z0 = p3[2] - c.target[2];
    const cy = Math.cos(c.yaw), sy = Math.sin(c.yaw), cp = Math.cos(c.pitch), sp = Math.sin(c.pitch);
    const x1 = cy * x0 + sy * z0, z1 = -sy * x0 + cy * z0;      // yaw around vertical axis
    const y2 = cp * y0 - sp * z1, z2 = sp * y0 + cp * z1;        // pitch around horizontal axis
    const dist = 2.8 / c.zoom, depth = dist - z2;
    if (depth < 0.08) return null;                                // behind the camera
    const f = Math.min(W, H) * 0.95 / depth;
    return { x: W / 2 + x1 * f, y: H / 2 - y2 * f, s: 1 / depth, z: z2 };
  };
  const shape = (kind, x, y, r) => {
    ctx.beginPath();
    if (kind === 'figure') ctx.rect(x - r, y - r, 2 * r, 2 * r);
    else if (kind === 'table') { const h = r * 1.2; ctx.moveTo(x, y - h); ctx.lineTo(x + h, y + h * .8); ctx.lineTo(x - h, y + h * .8); ctx.closePath(); }
    else ctx.arc(x, y, r, 0, Math.PI * 2);
  };
  const draw = () => {
    ctx.clearRect(0, 0, W, H); ctx.fillStyle = colors.surface; ctx.fillRect(0, 0, W, H);
    projected = [];
    for (const p of d.points) { const q = project(p.p3); if (q) projected.push({ p, ...q }); }
    projected.sort((a, b) => a.z - b.z); // far to near (painter's order)
    const sel = L.selected ? d.byId[L.selected] : null;
    if (sel) {
      const a = project(sel.p3);
      if (a) {
        ctx.save(); ctx.strokeStyle = colors.ink2; ctx.lineWidth = 1.5; ctx.setLineDash([3, 3]);
        for (const id of sel.neighbors) { const n = d.byId[id], b = n && project(n.p3); if (b) { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); } }
        ctx.restore();
      }
    }
    for (const q of projected) {
      const slot = q.p.cluster >= 0 ? landSlot(q.p.cluster) : -1;
      const r = Math.max(1.6, Math.min(7, (slot >= 0 ? 4.4 : 3.2) * Math.sqrt(q.s * 2.8)));
      ctx.globalAlpha = slot >= 0 ? 1 : active ? 0.32 : Math.max(0.45, Math.min(1, q.s * 2.4));
      ctx.fillStyle = slot >= 0 ? colors.s[slot] : colors.neutral;
      shape(q.p.kind, q.x, q.y, r); ctx.fill();
      ctx.globalAlpha = 1;
      if (slot >= 0 || q.p.id === L.selected) { ctx.lineWidth = q.p.id === L.selected ? 2.5 : 1; ctx.strokeStyle = q.p.id === L.selected ? colors.ink : colors.surface; ctx.stroke(); }
      q.r = r;
    }
    const labelled = active ? d.clusters.filter(c => landSlot(c.id) >= 0) : [...d.clusters].sort((a, b) => b.size - a.size).slice(0, 8);
    ctx.font = `${active ? 700 : 600} ${active ? 13 : 12}px ${cv('--font') || 'system-ui'}`; ctx.textAlign = 'center'; ctx.lineJoin = 'round';
    for (const c of labelled) {
      const q = project(c.p3); if (!q) continue;
      ctx.lineWidth = 4; ctx.strokeStyle = colors.surface; ctx.strokeText(c.label, q.x, q.y - 10);
      ctx.fillStyle = active ? colors.ink : colors.ink2; ctx.fillText(c.label, q.x, q.y - 10);
    }
  };
  const pick = (mx, my) => {
    let best = null, bestD = 12 * 12;
    for (let i = projected.length - 1; i >= 0; i--) { // nearest-first
      const q = projected[i], dx = q.x - mx, dy = q.y - my, dd = dx * dx + dy * dy;
      if (dd < Math.max(bestD, (q.r + 3) ** 2) && dd < bestD) { best = q; bestD = dd; }
    }
    return best;
  };
  // Fly to a newly highlighted topic.
  let fly = null;
  if (L.flyTo !== undefined && L.flyTo !== null) {
    const c = d.byCluster[L.flyTo];
    if (c) fly = { from: { ...L.cam, target: [...L.cam.target] }, to: { target: c.p3, zoom: Math.max(L.cam.zoom, 2.2) }, t0: performance.now(), ms: reduced ? 0 : 700 };
    L.flyTo = null; L.spin = false;
  }
  const loop = now => {
    if (!canvas.isConnected || !isLandscape()) { L.raf = 0; return; }
    if (fly) {
      const t = fly.ms ? Math.min(1, (now - fly.t0) / fly.ms) : 1, e = t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      L.cam.target = fly.from.target.map((v, i) => v + (fly.to.target[i] - v) * e);
      L.cam.zoom = fly.from.zoom + (fly.to.zoom - fly.from.zoom) * e; dirty = true;
      if (t >= 1) fly = null;
    }
    if (L.spin) { L.cam.yaw += 0.0025; dirty = true; }
    if (dirty) { draw(); dirty = false; }
    L.raf = requestAnimationFrame(loop);
  };
  // Interaction: drag to rotate, wheel/pinch to zoom, click to select.
  const pointers = new Map(); let moved = 0, pinch0 = 0, zoom0 = 1;
  const stopSpin = () => { if (L.spin) { L.spin = false; el.querySelector('#land-spin').textContent = 'Spin'; } };
  canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); pointers.set(e.pointerId, { x: e.clientX, y: e.clientY }); moved = 0; tip.hidden = true;
    if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch0 = Math.hypot(a.x - b.x, a.y - b.y); zoom0 = L.cam.zoom; } });
  canvas.addEventListener('pointermove', e => {
    const prev = pointers.get(e.pointerId);
    if (!prev) { // hover
      const box = canvas.getBoundingClientRect(), q = pick(e.clientX - box.left, e.clientY - box.top);
      if (!q) { tip.hidden = true; canvas.style.cursor = 'grab'; return; }
      canvas.style.cursor = 'pointer'; const p = q.p;
      tip.innerHTML = `<strong>${esc(p.label || KIND_LABEL[p.kind])}</strong> · ${esc(p.filename)}${p.page ? `, p. ${esc(p.page)}` : ''}<br><span class="muted">${esc(p.investigation ? invName(p.investigation) : '')}${p.cluster >= 0 ? ` · ${esc(topicName(p.cluster))}` : ''}</span><br>${esc(p.snippet.slice(0, 160))}${p.snippet.length > 160 ? '…' : ''}`;
      tip.hidden = false; tip.style.left = `${Math.max(0, Math.min(q.x + 14, box.width - 300))}px`; tip.style.top = `${Math.min(q.y + 14, box.height - 120)}px`;
      return;
    }
    const dx = e.clientX - prev.x, dy = e.clientY - prev.y; moved += Math.abs(dx) + Math.abs(dy);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) { const [a, b] = [...pointers.values()]; const dist = Math.hypot(a.x - b.x, a.y - b.y); if (pinch0) L.cam.zoom = Math.min(10, Math.max(0.5, zoom0 * dist / pinch0)); }
    else { L.cam.yaw += dx * 0.008; L.cam.pitch = Math.max(-1.5, Math.min(1.5, L.cam.pitch + dy * 0.008)); }
    if (moved > 3) { stopSpin(); canvas.style.cursor = 'grabbing'; }
    dirty = true;
  });
  const release = e => {
    const wasClick = pointers.size === 1 && moved <= 3; pointers.delete(e.pointerId); if (pointers.size < 2) pinch0 = 0; canvas.style.cursor = 'grab';
    if (wasClick && e.type === 'pointerup') { const box = canvas.getBoundingClientRect(), q = pick(e.clientX - box.left, e.clientY - box.top); if (q) { stopSpin(); selectLandItem(q.p.id); } }
  };
  canvas.addEventListener('pointerup', release); canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('pointerleave', () => { if (!pointers.size) tip.hidden = true; });
  canvas.addEventListener('wheel', e => { e.preventDefault(); stopSpin(); L.cam.zoom = Math.min(10, Math.max(0.5, L.cam.zoom * Math.exp(-e.deltaY * 0.0015))); dirty = true; }, { passive: false });
  canvas.addEventListener('dblclick', () => { L.cam = CAM_HOME(); dirty = true; });
  canvas.addEventListener('keydown', e => {
    const k = e.key, step = 0.12;
    if (k === 'ArrowLeft') L.cam.yaw -= step; else if (k === 'ArrowRight') L.cam.yaw += step;
    else if (k === 'ArrowUp') L.cam.pitch = Math.max(-1.5, L.cam.pitch - step); else if (k === 'ArrowDown') L.cam.pitch = Math.min(1.5, L.cam.pitch + step);
    else if (k === '+' || k === '=') L.cam.zoom = Math.min(10, L.cam.zoom * 1.2); else if (k === '-' || k === '_') L.cam.zoom = Math.max(0.5, L.cam.zoom / 1.2);
    else if (k === '0') L.cam = CAM_HOME(); else return;
    e.preventDefault(); stopSpin(); dirty = true;
  });
  el.querySelector('#land-spin').addEventListener('click', e => { L.spin = !L.spin; e.currentTarget.textContent = L.spin ? 'Pause spin' : 'Spin'; });
  el.querySelector('#land-reset').addEventListener('click', () => { L.cam = CAM_HOME(); dirty = true; });
  new ResizeObserver(resize).observe(canvas);
  resize();
  L.raf = requestAnimationFrame(loop);
}
function dimSwitchHTML() {
  const on = state.land.view === 'three';
  return `<div class="map-dim ui-switch"><span class="ui-switch-label${on ? '' : ' active'}">2D</span><button type="button" class="ui-switch-track" role="switch" aria-checked="${on}" aria-label="3-D view" data-land-dim><span class="ui-switch-knob"></span></button><span class="ui-switch-label${on ? ' active' : ''}">3D</span></div>`;
}
function bindDimSwitch(el) {
  el.querySelector('[data-land-dim]')?.addEventListener('click', () => { const L = state.land; L.view = L.view === 'three' ? 'chart' : 'three'; drawLandscapeView(); el.querySelector('[data-land-dim]')?.focus(); });
}
function selectLandItem(id) {
  state.land.selected = id;
  drawLandscapeView(); renderLandscapeDetail();
  main.querySelector('#land-detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function landItemHTML(p) {
  return `<strong>${esc(p.label || KIND_LABEL[p.kind])}</strong> · <a href="${docLink(p.source_id, p.page)}" target="_blank" rel="noopener">${esc(p.filename)}${p.page ? `, page ${esc(p.page)}` : ''}</a>${p.investigation ? ` <span class="muted small">${esc(invName(p.investigation))}</span>` : ''}`;
}
function renderLandscapeDetail() {
  const el = main.querySelector('#land-detail'); if (!el) return;
  const d = state.land.data, p = state.land.selected && d.byId[state.land.selected];
  if (!p) { el.innerHTML = ''; return; }
  const topic = p.cluster >= 0 ? d.byCluster[p.cluster] : null;
  const related = p.neighbors.map(id => d.byId[id]).filter(Boolean);
  el.innerHTML = `<section class="card"><div class="row"><h3 style="margin:0">${esc(p.label || KIND_LABEL[p.kind])}</h3>${p.kind === 'figure' ? '<span class="pill warn">AI figure description</span>' : ''}<span class="spacer"></span><button class="btn small" type="button" id="land-close">Close</button></div>
    <p style="margin-top:12px">${landItemHTML(p)}</p>
    <blockquote class="small">${esc(p.snippet)}${p.snippet.length >= 240 ? '…' : ''}</blockquote>
    ${topic ? `<p><span class="muted">Topic:</span> <strong>${esc(topic.label)}</strong>${p.core ? '' : ' <span class="muted small">(loosely)</span>'}${topic.description ? ` · <span class="small">${esc(topic.description)}</span>` : ''}</p>
      <div class="row"><button class="btn small" type="button" id="land-highlight">${landSlot(topic.id) >= 0 ? 'Remove topic highlight' : 'Highlight this topic'}</button><button class="btn small primary" type="button" id="land-ask">Ask about “${esc(topic.label)}”</button></div>` : '<p class="muted small">This item does not belong to a clear topic.</p>'}
    <h4 style="margin-top:20px">Related evidence <span class="muted small">(most similar passages)</span></h4>
    <ul class="plain">${related.map(r => `<li style="margin-bottom:10px"><button type="button" class="linklike" data-related="${esc(r.id)}">Show on map</button> ${landItemHTML(r)}<br><span class="small muted">${esc(r.snippet.slice(0, 180))}${r.snippet.length > 180 ? '…' : ''}</span></li>`).join('')}</ul></section>`;
  el.querySelector('#land-close').addEventListener('click', () => { state.land.selected = null; drawLandscapeView(); renderLandscapeDetail(); });
  el.querySelector('#land-highlight')?.addEventListener('click', () => toggleTopic(topic.id));
  el.querySelector('#land-ask')?.addEventListener('click', () => askQuestion(`What does the collection report about ${topic.label.toLowerCase()}?`));
  el.querySelectorAll('[data-related]').forEach(b => b.addEventListener('click', () => selectLandItem(b.dataset.related)));
}

// ---------- sources ----------
// Sources, organized by the three kinds of fire NASA studied in orbit.
const EXPERIMENT_TYPES = [
  { key: 'bass', grid: 'bass', title: 'BASS and BASS-II: burning solid materials', investigations: ['PSI-26', 'PSI-25'], families: ['bass', 'bass-ii'],
    text: 'Burning and Suppression of Solids. Small samples of solid materials, such as PMMA plastic rods and sheets and cotton-fiberglass fabric, were burned in a small flow duct inside the International Space Station’s Microgravity Science Glovebox. Crews varied airflow, oxygen and sample shape to see how flames spread, how they go out, and how readily materials burn without gravity.' },
  { key: 'flex', grid: 'flex', title: 'FLEX: burning fuel droplets', investigations: ['PSI-69', 'PSI-68'], families: ['flex'],
    text: 'Flame Extinguishment Experiment. Single droplets of liquid fuel, such as heptane and methanol, free-floating or held on a thin fiber, were ignited in the station’s Combustion Integrated Rack. Without buoyancy the flame forms a sphere around the droplet, which makes it possible to measure burning rates, extinction, and the effect of diluent gases such as helium and carbon dioxide.' },
  { key: 'saffire', grid: 'saffire', title: 'Saffire: spacecraft-scale fires', investigations: ['SAFFIRE', 'PSI-98', 'PSI-99', 'PSI-100'], families: ['saffire'],
    text: 'Spacecraft Fire Safety Demonstration. Large material samples were burned inside uncrewed Cygnus cargo vehicles after they left the space station, so fire growth could be studied at a realistic spacecraft scale with no risk to crews.' },
];
const psiLink = id => /^PSI-\d+$/.test(id) ? `https://psi.nasa.gov/physci/repo/data/investigations/${id}` : '';
function sourceRunsTable(records) {
  const cov = state.coverage, fields = (cov.fields || []).filter(f => records.some(r => Number.isFinite(r[f.key]))).slice(0, 5);
  return `<div class="table-scroll"><table><thead><tr><th>Test</th><th>Material</th>${fields.map(f => `<th class="num">${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''}</th>`).join('')}<th>Status</th><th>Source table</th></tr></thead><tbody>
    ${records.map(r => `<tr><td>${esc(r.test_id)}</td><td>${esc(r.material || '—')}</td>${fields.map(f => `<td class="num">${fmt(r[f.key])}</td>`).join('')}<td>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : '<span class="pill">Transcribed</span>'}</td><td class="small muted">${esc(r.source?.file || '')}</td></tr>`).join('')}
  </tbody></table></div>`;
}
function renderSources() {
  if (!state.corpus) { main.innerHTML = '<p class="loading">Loading sources…</p>'; Promise.all([loadCorpus(), loadCoverage()]).then(() => route() === 'sources' && renderSources()); return; }
  const docs = state.corpus.documents || [], cov = state.coverage, t = state.corpus.totals || {};
  const typeOf = d => EXPERIMENT_TYPES.find(x => (d.investigation_ids || []).some(i => x.investigations.includes(i)));
  const other = docs.filter(d => !typeOf(d));
  const docRow = d => `<li class="doc-row"><div class="doc-main"><strong>${esc(d.filename)}</strong><span class="muted small">${(d.investigation_ids || []).map(i => esc(invName(i))).join(', ')} · ${count(d.pages)} page${d.pages === 1 ? '' : 's'}${d.figures ? ` · ${count(d.figures)} figure${d.figures === 1 ? '' : 's'}` : ''}</span></div>
    <div class="row doc-links"><a class="small" href="${docLink(d.source_id)}" target="_blank" rel="noopener noreferrer">Open PDF ↗</a>${d.source_url ? `<a class="small" href="${safeURL(d.source_url)}" target="_blank" rel="noopener noreferrer">NASA record ↗</a>` : ''}</div></li>`;
  const section = x => {
    const mine = docs.filter(d => typeOf(d) === x);
    const runs = cov ? cov.records.filter(r => x.families.includes(String(r.family || '').toLowerCase())) : [];
    const reviewed = runs.filter(r => r.review_status === 'reviewed').length;
    const links = x.investigations.map(i => psiLink(i) ? `<a class="small" href="${psiLink(i)}" target="_blank" rel="noopener noreferrer">${esc(invName(i))} dataset ↗</a>` : '').filter(Boolean).join('');
    return `<section class="card source-type" id="src-${x.key}" aria-labelledby="src-${x.key}-h">
      <h2 id="src-${x.key}-h">${esc(x.title)}</h2>
      <p class="source-type-text">${esc(x.text)}</p>
      <div class="source-cols">
        <div><h3>Reports <span class="muted small">${count(mine.length)}</span></h3>${mine.length ? `<ul class="doc-list">${mine.map(docRow).join('')}</ul>` : '<p class="muted small">None indexed.</p>'}</div>
        <div><h3>Experiment data</h3>
          ${runs.length ? `<p class="source-stat"><strong>${count(runs.length)}</strong> experiment runs from NASA PSI tables${reviewed ? `, <strong>${count(reviewed)}</strong> reviewed` : ''}.</p>` : '<p class="muted small">No experiment tables indexed.</p>'}
          <div class="row doc-links">${runs.length ? `<a class="btn small" href="#/coverage" data-src-grid="${x.grid}">Coverage heatmap →</a>` : ''}<a class="btn small" href="#/ask" data-src-ask="${esc(x.title.split(':')[0])}">Ask about ${esc(x.title.split(':')[0])}</a></div>
          ${links ? `<div class="row doc-links" style="margin-top:8px">${links}</div>` : ''}
          ${runs.length ? `<details class="source-runs"><summary>Experiment runs (${count(runs.length)})</summary>${sourceRunsTable(runs)}</details>` : ''}
        </div>
      </div></section>`;
  };
  main.innerHTML = pageHead('Sources', 'What the atlas draws on', `${count(t.documents || docs.length)} NASA reports and ${count(cov?.records?.length || 0)} experiment runs from three kinds of fire experiments flown in orbit. Every answer links back to these pages and tables.`) + `
  <nav class="row source-jump" aria-label="Experiment types">${EXPERIMENT_TYPES.map(x => `<a class="chip" href="#/sources" data-jump="src-${x.key}">${esc(x.title.split(':')[0])}</a>`).join('')}</nav>
  <div class="stack">${EXPERIMENT_TYPES.map(section).join('')}
  ${other.length ? `<section class="card source-type"><h2>Other documents</h2><ul class="doc-list">${other.map(docRow).join('')}</ul></section>` : ''}</div>`;
  main.querySelectorAll('[data-jump]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); main.querySelector(`#${a.dataset.jump}`)?.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); }));
  main.querySelectorAll('[data-src-grid]').forEach(a => a.addEventListener('click', () => { state.cov.grid = a.dataset.srcGrid; }));
  main.querySelectorAll('[data-src-ask]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); askQuestion(`What did the ${a.dataset.srcAsk} experiments study and find?`); }));
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
      : 'Text search and cited answers work immediately; figures in uploads are not described automatically.'}</p>
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
        status.querySelector('#ask-upload').addEventListener('click', () => { state.ask.draft = ''; location.hash = '#/ask'; });
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
// Explore menu in the header: click to open; closes on choice, outside click or Escape.
{
  const btn = document.querySelector('.nav-drop-btn'), menu = document.querySelector('#explore-menu');
  const setOpen = open => { menu.hidden = !open; btn.setAttribute('aria-expanded', String(open)); };
  btn.addEventListener('click', e => { e.stopPropagation(); setOpen(menu.hidden); if (!menu.hidden) menu.querySelector('a')?.focus(); });
  menu.addEventListener('click', () => setOpen(false));
  document.addEventListener('click', e => { if (!e.target.closest('.nav-drop')) setOpen(false); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menu.hidden) { setOpen(false); btn.focus(); } });
  window.addEventListener('hashchange', () => setOpen(false));
}
document.querySelector('.nav-toggle').addEventListener('click', e => {
  const nav = document.querySelector('#site-nav'), open = !nav.classList.contains('open');
  nav.classList.toggle('open', open); e.currentTarget.setAttribute('aria-expanded', String(open));
});
window.addEventListener('hashchange', () => { render(); main.focus({ preventScroll: true }); window.scrollTo(0, 0); });
async function start() {
  try { state.me = await api('/api/me'); } catch { state.me = { name: null, is_admin: false }; }
  render();
  await Promise.all([loadCorpus(), loadCoverage()]);
  if (route() === 'home' || route() === 'sources') render();
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
loadLimits().then(() => { if (route() === 'ask' && !state.ask.loading) renderAsk(); });
start();
