// Combustion Atlas public UI. Self-contained; talks only to this server's /api.
const main = document.querySelector('#main');
const state = {
  me: null, corpus: null, coverage: null, coverageError: '', options: null, optionsError: '',
  ask: { mode: 'answer', question: '', loading: false, error: '', result: null, progress: [] },
  cov: { x: 'oxygen_pct', y: 'flow_cm_s', slots: [null, null, null], view: 'chart', detail: null, initialized: false },
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
  document.querySelectorAll('.admin-only').forEach(el => { el.hidden = !state.me?.is_admin; });
  const badge = document.querySelector('#user-badge');
  badge.innerHTML = state.me?.name ? `${esc(state.me.name)}${state.me.is_admin ? '<span class="pill">Admin</span>' : ''}` : (state.me?.is_admin ? '<span class="pill">Local admin</span>' : '');
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
      <h1>Ask decades of NASA microgravity-combustion research.</h1>
      <p class="lead">Combustion Atlas makes NASA's spacecraft fire-safety experiments searchable and comparable: every answer quotes the original report and page, and the coverage map shows where the evidence is thin.</p>
      <form class="hero-search" id="hero-search" role="search">
        <label for="hero-q" class="visually-hidden" hidden>Question</label>
        <input id="hero-q" type="search" maxlength="1000" placeholder="e.g. How does opposed-flow velocity affect flame spread?" aria-label="Ask a question">
        <button class="btn primary" type="submit">Ask</button>
      </form>
    </div>
    <div class="hero-art" aria-hidden="true"></div>
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
  </section>
  <section class="section">
    <div class="grid cols-${state.me?.is_admin ? 4 : 3}">
      ${tile('#/ask', '?', 'Ask a question', 'Get answers built only from indexed NASA documents, with every claim linked to its page. Or plan next research steps.')}
      ${tile('#/coverage', '◎', 'Experiment coverage', 'See which conditions have been tested across investigations, and where this collection has no runs.')}
      ${tile('#/predict', '≈', 'Prediction', 'Enter conditions to find the closest observed runs and a statistical estimate, or “insufficient data”.')}
      ${state.me?.is_admin ? tile('#/upload', '+', 'Add to corpus', 'Upload a NASA report or paper (PDF). Visible to administrators only.') : ''}
    </div>
  </section>`;
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
const EXAMPLES = {
  answer: ['Which variables were tested in BASS-II?', 'How many samples were burned in BASS-II?', 'Which components are labelled in Figure 5.1 of the BASS-II duct schematic?', 'How does opposed-flow velocity affect flame spread over thin PMMA?'],
  plan: ['Flame spread over thin PMMA at low opposed-flow velocity and reduced oxygen', 'Flammability limits of PMMA rods in microgravity', 'Smoke particle size from overheated spacecraft materials'],
};
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
    <div class="row"><button class="btn primary" type="submit" ${a.loading ? 'disabled' : ''}>${a.loading ? (a.mode === 'answer' ? 'Searching…' : 'Analyzing…') : (a.mode === 'answer' ? 'Get answer' : 'Find next steps')}</button>
      <span class="hint" style="margin:0">Takes a few seconds${a.mode === 'plan' ? ' to a minute' : ''}.</span></div>
    <div class="chips" aria-label="Examples">${EXAMPLES[a.mode].map(q => `<button type="button" class="chip" data-example="${esc(q)}">${esc(q)}</button>`).join('')}</div>
  </form>
  <div id="ask-results" class="section" aria-live="polite">${askResults()}</div>`;
  main.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => { if (a.loading) return; state.ask.question = main.querySelector('#q').value; Object.assign(a, { mode: b.dataset.mode, result: null, error: '' }); renderAsk(); }));
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
      ? { kind: 'answer', ...(await streamAnswer(a.question)) }
      : { kind: 'plan', ...(await postJSON('/api/directions', { topic: a.question, allow_provider_calls: true })) };
  } catch (e) { a.error = e.message; }
  a.loading = false;
  if (route() === 'ask') renderAsk();
}
// Streams NDJSON progress from /api/ask/stream; falls back to /api/ask when the route is absent.
async function streamAnswer(question) {
  const body = { question, method: 'hybrid', generate_answer: true, allow_provider_calls: true };
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
  const label = failed ? `Stopped after ${total} s` : `Answered in ${total} s`;
  return `<details class="card steps-summary"><summary><span>${failed ? '⚠' : '✓'} ${esc(label)}</span><span class="muted small">${steps.length} step${steps.length === 1 ? '' : 's'}</span></summary>
    <ol class="steps">${steps.map(s => `<li class="done"><span>${esc(s.message)}</span><span class="muted small">${fmt(s.elapsed_s, 3)} s</span></li>`).join('')}</ol></details>`;
}
function updateProgress() { const el = main.querySelector('#ask-results'); if (el && route() === 'ask' && state.ask.loading) el.innerHTML = progressHTML(); }
function citeHTML(support, byId) {
  const src = byId[support.chunk_id] || {};
  const card = src.record_card;
  const where = card
    ? `<span class="pill ok">Table record · ${esc(card.review_action)}</span> <span>${esc(card.locator || src.filename || 'Reviewed evidence')}</span>${card.open_questions ? ` · <span class="pill warn">${esc(card.open_questions)} open question${card.open_questions === 1 ? '' : 's'}</span>` : ''}`
    : src.source_id ? `<a href="${docLink(src.source_id, src.physical_page)}" target="_blank" rel="noopener noreferrer">${esc(src.filename || 'Source')}, page ${esc(src.physical_page)} ↗</a>` : esc(support.chunk_id);
  const visual = src.visual ? ` · <span class="pill warn">${esc(src.visual.kind)} ${esc(src.visual.label)} · unreviewed AI description</span>` : '';
  const crop = src.visual && String(src.crop_url || '').startsWith('/api/visuals/') ? `<details><summary class="cite">View original page image</summary><img class="crop" loading="lazy" src="${esc(src.crop_url)}" alt="Original page for ${esc(src.visual.kind)} ${esc(src.visual.label)}"></details>` : '';
  return `<blockquote>${esc(support.quote)}</blockquote><div class="cite">${where}${visual}</div>${crop}`;
}
function sourcesSummary(results) {
  if (!results?.length) return '';
  const docs = new Set(results.map(r => r.source_id));
  return `<section class="card"><div class="section-head"><h3>Sources searched</h3><span class="muted small">${results.length} passages · ${docs.size} document${docs.size === 1 ? '' : 's'}</span></div>
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
    if (!ans) return sourcesSummary(results);
    const partial = ans.status === 'answered' && (ans.limitations || []).length > 0;
    const status = ans.status !== 'answered' ? '<span class="pill bad">Insufficient evidence</span>' : partial ? '<span class="pill warn">Partial evidence</span>' : '<span class="pill ok">Answered from sources</span>';
    const body = ans.status !== 'answered'
      ? `<p>The indexed documents do not support an answer to this question. That means it is missing from this collection, not that it was never studied.</p>`
      : ans.claims.map(c => `<div class="claim"><p>${esc(c.text)}</p>${c.supports.map(s => citeHTML(s, byId)).join('')}</div>`).join('');
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
  const head = pageHead('Coverage', 'Experiment coverage', 'Each mark is one experiment run, placed by its test conditions. Dashed regions have no runs in this collection. That shows where this collection is thin, not that a condition is unstudied.');
  if (state.coverageError) { main.innerHTML = head + emptyBox('Not available yet', state.coverageError); return; }
  initCoverageSelection();
  const cov = state.coverage, c = state.cov;
  const fields = (cov.fields || []).filter(f => f.count > 0);
  const fieldOpt = sel => fields.map(f => `<option value="${esc(f.key)}" ${sel === f.key ? 'selected' : ''}>${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''} · ${count(f.count)}</option>`).join('');
  const reviewed = cov.records.filter(r => r.review_status === 'reviewed').length;
  const famChips = (cov.families || []).map(f => {
    const slot = slotOf(f.key);
    const sw = slot >= 0 ? legendShape(SHAPES[slot], `var(--s${slot + 1})`) : legendShape('circle', 'var(--neutral)');
    return `<button type="button" class="chip" data-family="${esc(f.key)}" aria-pressed="${slot >= 0}">${sw}${esc(f.label)} <span class="muted">${count(f.count)}</span></button>`;
  }).join('');
  main.innerHTML = head + `
  <div class="row" style="margin-bottom:16px"><span class="pill warn">${count(cov.records.length - reviewed)} unreviewed candidate runs</span>${reviewed ? `<span class="pill ok">${count(reviewed)} reviewed</span>` : ''}${(cov.notes || []).map(n => `<span class="muted small">${esc(n)}</span>`).join('')}</div>
  <section class="card">
    <div class="controls">
      <div class="field"><label for="cov-x">Horizontal axis</label><select id="cov-x">${fieldOpt(c.x)}</select></div>
      <div class="field"><label for="cov-y">Vertical axis</label><select id="cov-y">${fieldOpt(c.y)}</select></div>
      <span class="spacer"></span>
      <div class="segmented" role="group" aria-label="View"><button type="button" data-view="chart" aria-pressed="${c.view === 'chart'}">Chart</button><button type="button" data-view="table" aria-pressed="${c.view === 'table'}">Table</button></div>
    </div>
    <div><label>Highlight up to three families</label><div class="chips family-chips" role="group" aria-label="Families">${famChips || '<span class="muted">No families yet.</span>'}</div></div>
    <div id="cov-view" style="margin-top:16px"></div>
  </section>
  <div id="cov-detail" class="section" aria-live="polite"></div>`;
  main.querySelector('#cov-x').addEventListener('change', e => { c.x = e.target.value; drawCoverageView(); });
  main.querySelector('#cov-y').addEventListener('change', e => { c.y = e.target.value; drawCoverageView(); });
  main.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => { c.view = b.dataset.view; renderCoverage(); }));
  main.querySelectorAll('[data-family]').forEach(b => b.addEventListener('click', () => {
    const key = b.dataset.family, slot = slotOf(key);
    if (slot >= 0) c.slots[slot] = null; // freeing a slot never repaints the others
    else { const free = c.slots.indexOf(null); if (free < 0) { toastInline('Three families are highlighted. Deselect one first.'); return; } c.slots[free] = key; }
    renderCoverage();
  }));
  drawCoverageView();
  renderCoverageDetail();
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
  if (c.view === 'table') { el.innerHTML = coverageTable(cov.records); bindRows(el); return; }
  if (!plotted.length) { el.innerHTML = emptyBox('Nothing to plot', `No runs have both ${fx.label} and ${fy.label}. Try other axes or the table view.`); return; }
  const W = 880, H = 500, m = { l: 64, r: 20, t: 16, b: 56 };
  const gaps = (cov.gaps || []).filter(g => (g.x_field === c.x && g.y_field === c.y) || (g.x_field === c.y && g.y_field === c.x))
    .map(g => g.x_field === c.x ? g : { ...g, x_range: g.y_range, y_range: g.x_range });
  const xs = [...plotted.map(r => r[c.x]), ...gaps.flatMap(g => g.x_range)], ys = [...plotted.map(r => r[c.y]), ...gaps.flatMap(g => g.y_range)];
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
  const legendItems = state.cov.slots.map((k, i) => k ? `<span>${legendShape(SHAPES[i], `var(--s${i + 1})`)}${esc(familyLabel(k))}</span>` : '').join('') + `<span>${legendShape('circle', 'var(--neutral)')}Other families</span><span><svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="var(--neutral)" stroke="var(--ink)" stroke-width="2"/></svg>Reviewed (dark ring)</span>${gaps.length ? '<span><svg width="22" height="14" aria-hidden="true"><rect x="1" y="1" width="20" height="12" rx="3" fill="none" stroke="var(--ink-2)" stroke-dasharray="4 3"/></svg>No runs in this collection</span>' : ''}`;
  el.innerHTML = `<div class="chart-wrap"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Scatter of ${plotted.length} runs: ${fy.label} against ${fx.label}`)}">${grid}${gapSVG}${axes}${marks}</svg><div class="tooltip" id="cov-tip" hidden></div></div>
    <div class="legend" aria-label="Legend">${legendItems}</div>
    ${missing ? `<p class="hint">${count(missing)} runs lack ${esc(fx.label)} or ${esc(fy.label)} and are not plotted; they appear in the table view.</p>` : ''}
    ${gaps.length ? `<ol class="small" style="margin-top:12px">${gaps.map(g => `<li>${esc(g.note)}</li>`).join('')}</ol>` : ''}`;
  const tip = el.querySelector('#cov-tip'), svg = el.querySelector('svg');
  const byId = Object.fromEntries(cov.records.map(r => [String(r.id), r]));
  el.querySelectorAll('.hit').forEach(g => {
    const r = byId[g.dataset.id];
    const show = ev => {
      const box = svg.getBoundingClientRect();
      tip.innerHTML = `<strong>${esc(familyLabel(r.family))} · ${esc(r.test_id)}</strong><br>${esc(fx.label)}: ${fmt(r[c.x])}${fx.unit ? ` ${esc(fx.unit)}` : ''}<br>${esc(fy.label)}: ${fmt(r[c.y])}${fy.unit ? ` ${esc(fy.unit)}` : ''}${r.material ? `<br>Material: ${esc(r.material)}` : ''}<br><span class="muted">${r.review_status === 'reviewed' ? 'Reviewed' : 'Unreviewed candidate'} · click for details</span>`;
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
}
function coverageTable(records) {
  const cols = ['oxygen_pct', 'flow_cm_s', 'pressure_kpa'].map(fieldMeta);
  return `<div class="table-scroll"><table><caption class="visually-hidden" hidden>Experiment runs</caption><thead><tr><th>Family</th><th>Test</th><th>Material</th>${cols.map(f => `<th class="num">${esc(f.label)}${f.unit ? ` (${esc(f.unit)})` : ''}</th>`).join('')}<th>Gravity</th><th>Status</th><th>Source</th></tr></thead><tbody>
    ${records.map(r => `<tr data-row="${esc(r.id)}" tabindex="0" style="cursor:pointer"><td>${esc(familyLabel(r.family))}</td><td>${esc(r.test_id)}</td><td>${esc(r.material || '—')}</td>${cols.map(f => `<td class="num">${fmt(r[f.key])}</td>`).join('')}<td>${esc(r.gravity || '—')}</td><td>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : '<span class="pill warn">Unreviewed</span>'}</td><td class="small">${esc(r.source?.file || '')}${r.source?.record != null ? `, record ${esc(r.source.record)}` : ''}</td></tr>`).join('')}
  </tbody></table></div>`;
}
function bindRows(el) { el.querySelectorAll('[data-row]').forEach(tr => { const open = () => { state.cov.detail = tr.dataset.row; renderCoverageDetail(); }; tr.addEventListener('click', open); tr.addEventListener('keydown', e => { if (e.key === 'Enter') open(); }); }); }
function renderCoverageDetail() {
  const el = main.querySelector('#cov-detail'); if (!el) return;
  const r = state.coverage.records.find(x => String(x.id) === String(state.cov.detail));
  if (!r) { el.innerHTML = ''; return; }
  const row = (k, v) => v == null || v === '' ? '' : `<dt>${esc(k)}</dt><dd>${v}</dd>`;
  const outcomes = Object.entries(r.outcomes || {});
  el.innerHTML = `<section class="card"><div class="row"><h3 style="margin:0">${esc(familyLabel(r.family))} · ${esc(r.test_id)}</h3>${r.review_status === 'reviewed' ? '<span class="pill ok">Reviewed</span>' : '<span class="pill warn">Unreviewed candidate</span>'}<span class="spacer"></span><button class="btn small" type="button" id="close-detail">Close</button></div>
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
function renderUpload() {
  const head = pageHead('Administrator', 'Add to corpus', 'Upload a NASA report or paper (PDF). Pages are extracted and added without changing existing documents.');
  if (!state.me?.is_admin) { main.innerHTML = head + emptyBox('Administrator access required', 'Only the project administrator can add documents.'); return; }
  main.innerHTML = head + `
  <form class="card" id="upload-form" style="max-width:720px">
    <div class="field"><label for="u-file">PDF file (up to 80 MB)</label><input id="u-file" type="file" accept="application/pdf,.pdf" required></div>
    <div class="field"><label for="u-inv">Investigation ID</label><input id="u-inv" required maxlength="79" placeholder="e.g. PSI-25 or SAFFIRE-II" style="width:100%"></div>
    <div class="field"><label for="u-url">Source URL (optional)</label><input id="u-url" type="url" placeholder="https://ntrs.nasa.gov/citations/…" style="width:100%"></div>
    <div class="field"><label style="font-weight:500"><input id="u-embed" type="checkbox" checked> Make it searchable by meaning (sends extracted text to OpenAI for embeddings)</label></div>
    <button class="btn primary" type="submit">Add to corpus</button>
    <p class="hint">Figures are not described automatically yet; text search and cited answers work immediately.</p>
    <div id="u-status" aria-live="polite"></div>
  </form>`;
  const form = main.querySelector('#upload-form');
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const file = form.querySelector('#u-file').files[0], status = form.querySelector('#u-status'), button = form.querySelector('button[type=submit]');
    if (!file) return;
    if (file.size > 80 * 1024 * 1024) { status.innerHTML = '<div class="error">The PDF is larger than 80 MB.</div>'; return; }
    const params = new URLSearchParams({ filename: file.name, investigation: form.querySelector('#u-inv').value.trim(), source_url: form.querySelector('#u-url').value.trim(), embed: form.querySelector('#u-embed').checked ? '1' : '0' });
    button.disabled = true; status.innerHTML = '<p class="loading" style="padding:16px 0">Extracting and indexing pages… large reports can take a minute.</p>';
    try {
      const r = await api(`/api/upload?${params}`, { method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file });
      await loadCorpus(true);
      status.innerHTML = `<p class="notice">${r.status === 'unchanged' ? 'Already indexed — nothing changed.' : `Added <strong>${esc(r.filename)}</strong> (${esc(r.investigation_id)}): ${count(r.physical_pages)} pages, ${count(r.chunks_added)} passages, ${count(r.embedded_chunks)} embedded${r.sparse_pages ? `, ${count(r.sparse_pages)} sparse pages (possibly scanned)` : ''}.`}</p>`;
    } catch (err) { status.innerHTML = `<div class="error" role="alert">${esc(err.message)}</div>`; }
    button.disabled = false;
  });
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
start();
