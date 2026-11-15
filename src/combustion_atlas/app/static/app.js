const main = document.querySelector('#main');
const state = { overview: null, records: [], mappings: [], notes: [], sources: [], record: 'B1', tab: 'conditions', sourceFilter: '', sourceStatus: '', question: '', investigation: '', results: null, searching: false };
const names = { 'PSI-25': 'BASS-II', 'PSI-26': 'BASS', 'PSI-68': 'FLEX-2', 'PSI-101': 'SAME-R', 'PSI-102': 'SAME', 'PSI-69': 'FLEX', 'PSI-98': 'Saffire I', 'PSI-99': 'Saffire II', 'PSI-100': 'Saffire III' };
state.reviewDrafts = {};
state.filteredRecords = null;
state.structuredFilters = {scope:'candidates'};
state.filterError = '';
state.recordSources = {};
state.preservedRecords = [];
state.searchMethod = 'keyword';
state.generateAnswer = false;
state.allowProviderCalls = false;
state.ragStatus = {};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fieldNames = {ambient_gas:'Ambient gas',oxygen_mole_fraction:'O₂ mole fraction',droplet_diameter_mm:'Droplet diameter',burning_rate_constant:'Burning rate constant',residence_time_s:'Residence time',flame_temperature_k:'Flame temperature',material_description:'Material description',material:'Material',fuel_type:'Fuel',geometry:'Geometry',thickness_um:'Thickness',width_cm:'Width',oxygen_pct:'Initial O₂',initial_co2_pct:'Initial CO₂',initial_co_ppm:'Initial CO',final_oxygen_pct:'Final O₂',final_co2_pct:'Final CO₂',final_co_ppm:'Final CO',airflow_cm_s:'Airflow',pressure_kpa:'Pressure',gravity_regime:'Gravity regime',ignition_method:'Ignition method',suppressant:'Suppressant'};
const recordKey = record => `${record.identity.investigation_id}/${record.identity.test_id}`;
const pretty = value => fieldNames[value] || String(value).replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const count = value => Number(value ?? 0).toLocaleString();
const val = measure => measure?.value == null ? (measure?.qualifier === 'not_applicable_in_source' ? 'Not applicable (source)' : measure?.qualifier === 'missing_in_source' ? 'Missing (source)' : 'Unresolved') : `${measure.qualifier === 'approximate' ? '~ ' : ''}${esc(measure.value)}${measure.unit ? ` <small>${esc(measure.unit)}</small>` : ''}`;
const safeURL = value => { try { const u = new URL(value); return u.protocol === 'https:' ? esc(u.href) : '#'; } catch { return '#'; } };
const tag = (text, color = '') => `<span class="tag ${color}">${esc(text)}</span>`;
const optionList = selected => `<option value="">All investigations</option>${Object.entries(state.overview?.demo ? Object.fromEntries(state.sources.flatMap(s=>s.investigation_ids).map(id=>[id,id])) : {...names, ...Object.fromEntries((state.corpus?.documents||[]).flatMap(d=>d.investigation_ids).filter(id=>!names[id]).map(id=>[id,id]))}).map(([id, name]) => `<option value="${id}" ${selected === id ? 'selected' : ''}>${name} · ${id}</option>`).join('')}`;
const empty = (title, message) => `<div class="empty"><div class="empty-icon">⌕</div><h2>${esc(title)}</h2><p>${esc(message)}</p></div>`;
const heading = (eyebrow, title, description, action = '') => `${state.overview?.demo ? '<div class="notice"><strong>SYNTHETIC DEMO</strong> · Offline fixtures only. These are not NASA observations or scientifically approved records.</div>' : ''}<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${state.overview?.demo ? 'Explore synthetic records and unrelated toy documents in an isolated workspace.' : description}</p></div>${action}</div>`;


function presentRecord(record) {
  const source = state.recordSources[`${record.investigation_id}/${record.test_id}`] || {};
  const original = record.provenance[0] || {};
  const provenance = p => ({source_url:p.source_url, source_sha256:p.source_sha256,
    file:source.file_name || p.source_locator || 'Source reference', row:p.record_number,
    column:p.column_name, locator:p.source_locator});
  const raw = Object.entries(record.raw_cells).map(([column,value]) => ({
    original_value:value, provenance:provenance({...original,column_name:column})
  }));
  const c = record.conditions;
  const conditions = {};
  const text = (field,value,originalValue=value) => {
    conditions[field]={value,original_value:originalValue,provenance:provenance(original)};
  };
  if(c.material_original != null) text('material_description',c.material_original);
  text('material',c.material,c.material_original);
  text('geometry',c.geometry,c.material_original);
  for(const field of ['fuel_type','gravity_regime','ignition_method','suppressant'])
    if(c[field] != null) text(field,c[field]);
  Object.assign(conditions,c.dimensions,c.measurements);
  for(const field of ['oxygen_pct','pressure_kpa','airflow_cm_s','temperature'])
    if(c[field] != null) conditions[field]=c[field];
  return {identity:{investigation_id:record.investigation_id,test_id:record.test_id,sample_id:record.sample_id},
    conditions, outcomes:record.outcomes,
    instrument_settings:Object.fromEntries(Object.entries(record.instrument_settings).map(([k,v])=>[k,{original_value:v}])),
    extra_metadata:record.extra_metadata,raw_cells:raw,validation_status:record.validation_status,
    human_review_status:'unreviewed',issues:record.validation_messages.map(message=>({field:'Validation',message}))};
}

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'The request could not be completed.');
  return body;
}
function toast(message) {
  const el = document.querySelector('#toast'); el.textContent = message; el.classList.add('visible');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('visible'), 4500);
}
function route() { return location.hash.slice(1).split('/')[0] || 'ask'; }
function render() {
  const page = route()==='search' ? 'ask' : route();
  document.querySelectorAll('[data-nav]').forEach(link => { link.classList.toggle('active', link.dataset.nav === page); if (link.dataset.nav === page) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); });
  const review = ['overview','experiments','conditions','sources'].includes(page);
  const group = document.querySelector('.nav-group'); if(group && review) group.open = true;
  const titles = {ask:'Ask the corpus',corpus:'Corpus',directions:'Research directions',overview:'Review workspace / Overview',experiments:'Review workspace / Experiments',conditions:'Review workspace / Proposed conditions',sources:'Review workspace / Source library'};
  document.querySelector('#breadcrumb').textContent = titles[page] || 'Ask the corpus';
  ({ ask: renderSearch, corpus: renderCorpus, directions: renderDirections, overview: renderOverview, experiments: renderExperiments, sources: renderSources, conditions: renderConditions }[page] || renderSearch)();
}
function renderConditions() {
  main.innerHTML = heading('PROPOSED CONDITIONS','Find the evidence for your experiment.','Compare proposed conditions with recorded experiments and inspect supporting sources.') +
    `<section class="panel"><div class="panel-body"><h2>Condition matching is in candidate preview</h2><p>Filter candidate records by material, oxygen, pressure and airflow in the experiment browser.</p><p>Scientific comparability, mismatch ranking and coverage assessments will follow reviewed field meanings and approved records. Predictions are not currently available.</p><a class="btn primary" href="#experiments">Explore candidate conditions →</a> <a class="btn" href="#search">Ask the evidence →</a></div></section>`;
}
function recordRows() {
  return state.records.map(r => `<tr class="clickable" data-record="${esc(recordKey(r))}"><td><button class="btn link" data-record="${esc(recordKey(r))}">${esc(r.identity.test_id)} <span class="arrow">↗</span></button><small>${esc(r.identity.investigation_id)}</small></td><td>${esc(r.conditions.material?.value || r.conditions.fuel_type?.value || 'Unresolved')}<small>${esc(r.conditions.geometry?.value || 'See source description')}</small></td><td class="mono">${val(r.conditions.oxygen_pct || r.conditions.oxygen_mole_fraction)}</td><td>${tag(r.issues.length ? `${r.issues.length} review flag${r.issues.length === 1 ? '' : 's'}` : 'Checks passed', r.issues.length ? 'amber' : 'green')}</td></tr>`).join('');
}
function bindRecords() { main.querySelectorAll('[data-record]').forEach(el => el.addEventListener('click', e => { e.stopPropagation(); state.record = el.dataset.record; if (route() === 'experiments') renderExperiments(); else location.hash = 'experiments'; })); }
function renderOverview() {
  const o = state.overview;
  main.innerHTML = heading('EVIDENCE OBSERVATORY', 'Evidence, with context.', 'Explore combustion experiments. Follow the source. Keep uncertainty visible.', '<a class="btn primary" href="#experiments">Review experiments <span class="arrow">↗</span></a>') +
  `<div class="stats">${[
    ['Candidate experiments',o.experiments,`${o.human_unreviewed} awaiting scientific review`,'⌘',''],
    ['Records with flags',o.flagged,'Original values preserved','◌','emphasis'],
    ['Indexed documents',o.documents,`${count(o.pages)} document pages`,'▤',''],
    ['Searchable passages',o.chunks,'Page citations attached','⌕','']
  ].map(([label,note,foot,icon,cls]) => `<div class="stat ${cls}"><span class="stat-icon">${icon}</span><div class="stat-label">${label}</div><div class="stat-number">${count(note)}</div><div class="stat-foot">${foot}</div></div>`).join('')}</div>
  <div class="grid-two"><div><section class="panel"><div class="panel-head"><div><h2>Review candidates</h2><p>${o.demo ? 'Synthetic normalization fixture · Individual test runs' : 'NASA source extractions · Individual experimental runs'}</p></div>${tag('CANDIDATES','amber')}</div>
  ${state.records.length ? `<div class="table-scroll"><table><thead><tr><th>Test / source</th><th>Material</th><th>O₂ condition</th><th>Validation</th></tr></thead><tbody>${recordRows()}</tbody></table></div>` : empty('No candidates loaded','Candidate records will appear here after extraction.')}
  <div class="panel-footer"><span>Automated checks and human review are tracked separately.</span><a href="#experiments" class="btn link">Inspect records →</a></div></section>
  <section class="panel"><div class="panel-head"><h2>From source to evidence</h2>${tag('WORK IN PROGRESS')}</div><div class="panel-body pipeline">${[['01','Capture',state.sources.length?'Sources available':'Add source captures'],['02','Normalize','Scientific review open'],['03','Retrieve',o.index_ready?'Keyword search ready':'Index not built'],['04','Review','Drafts and adjudication']].map(([n,t,s]) => `<div class="pipeline-step"><span class="step-num">${n}</span><b>${t}</b><small>${s}</small></div>`).join('')}</div></section>
  <div class="notice">These records are extraction candidates. A passed automated check does not establish scientific meaning or human approval.</div></div>
  <div class="overview-side"><section class="panel"><div class="panel-head"><div><h2>Source collection</h2><p>Downloaded / selected files per investigation</p></div></div><div class="panel-body">${o.coverage.map(c => `<div class="coverage-item"><div class="coverage-label">${esc(c.name)} <span>${c.downloaded} / ${c.eligible}</span></div><div class="bar"><span style="width:${c.eligible ? c.downloaded/c.eligible*100 : 0}%"></span></div>${c.failed ? `<div class="coverage-foot">${c.failed} source file${c.failed===1?'':'s'} unavailable</div>` : ''}</div>`).join('')}</div><div class="panel-footer"><span>${count(o.files_discovered)} file entries discovered</span><a class="btn link" href="#sources">View library →</a></div></section>
  <div class="search-callout"><div class="eyebrow">BEYOND THE TABLES</div><h2>Find the scientific context.</h2><p>Search reports, methods and investigation documents with citations to the original pages.</p><a class="btn full-width" href="#search">Search documents <span class="arrow">→</span></a></div></div></div>`;
  bindRecords();
}
function filterControls() {
  const f=state.structuredFilters;
  const text=(key,label)=>`<label>${label}<input name="${key}" value="${esc(f[key] || '')}" placeholder="Any"></label>`;
  const numeric=(key,label)=>`<label>${label}<input name="${key}" type="number" min="0" step="any" value="${esc(f[key] ?? '')}" placeholder="Any"></label>`;
  return `<section class="panel"><form id="experiment-filters" class="panel-body"><div class="experiment-filters"><label>Record scope<select name="scope"><option value="candidates" ${f.scope==='candidates'?'selected':''}>Candidate preview</option></select></label>${text('material','Exact material')}${numeric('oxygen_min_pct','Min O₂ (%)')}${numeric('oxygen_max_pct','Max O₂ (%)')}<button class="btn primary" type="submit">Apply filters</button><button class="btn" type="button" id="clear-filters">Clear</button></div><details style="margin-top:14px;font-size:11px"><summary>More condition filters</summary><div class="experiment-filters" style="margin-top:15px">${text('geometry','Exact geometry')}${text('gravity_regime','Gravity regime')}${numeric('pressure_min_kpa','Min pressure (kPa)')}${numeric('pressure_max_kpa','Max pressure (kPa)')}${numeric('airflow_min_cm_s','Min airflow (cm/s)')}${numeric('airflow_max_cm_s','Max airflow (cm/s)')}</div></details><p class="form-hint">Ranges are inclusive. Unknown values and instrument display settings do not satisfy physical-condition filters. Matching is not a comparability judgment.</p>${state.filterError?`<div class="error" role="alert">${esc(state.filterError)}</div>`:''}</form></section>`;
}
function bindFilters() {
  const form=main.querySelector('#experiment-filters');
  form.addEventListener('submit',async e=>{
    e.preventDefault(); const button=form.querySelector('[type=submit]'); button.disabled=true;
    state.structuredFilters=Object.fromEntries(new FormData(form));
    const params=new URLSearchParams(Object.entries(state.structuredFilters).filter(([,value])=>value!==''));
    try { const result=await api(`/api/structured-search?${params}`); const extra = state.preservedRecords.filter(r => {
      const f=state.structuredFilters, c=r.conditions;
      for(const key of ['material','geometry','gravity_regime']) if(f[key] && String(c[key]?.value || '').toLowerCase() !== f[key].trim().toLowerCase()) return false;
      for(const [name,field,unit] of [['oxygen','oxygen_pct','%'],['pressure','pressure_kpa','kPa'],['airflow','airflow_cm_s','cm/s']]) {
        const suffix={oxygen:'pct',pressure:'kpa',airflow:'cm_s'}[name], lo=f[`${name}_min_${suffix}`], hi=f[`${name}_max_${suffix}`], m=c[field];
        if((lo!=='' && lo!=null || hi!=='' && hi!=null) && (m?.value == null || m.unit!==unit || lo && m.value<Number(lo) || hi && m.value>Number(hi))) return false;
      }
      return true;
    });
    state.filteredRecords=[...result.records.map(presentRecord),...extra]; state.filterError=''; }
    catch(err) { state.filterError=err.message; }
    if(route()==='experiments') renderExperiments();
  });
  form.querySelector('#clear-filters').addEventListener('click',()=>{state.structuredFilters={scope:'candidates'};state.filteredRecords=null;state.filterError='';renderExperiments();});
}
function renderExperiments() {
  const records = state.filteredRecords ?? state.records;
  const r = records.find(r => recordKey(r) === state.record) || records[0];
  if (!r) { main.innerHTML = heading('EXPERIMENTS','Individual runs, in context.','Inspect conditions, measured outcomes and the original source.') + filterControls() + empty('No matching records','Generate candidates or try broader condition filters.'); bindFilters(); return; }
  state.record = recordKey(r);
  const notes = state.notes.filter(n => n.test_id === r.identity.test_id && n.investigation_id === r.identity.investigation_id);
  const fields = state.tab === 'outcomes' ? r.outcomes.map(m => [m.outcome_type,m]) : state.tab === 'settings' ? Object.entries(r.instrument_settings).map(([k,m]) => [k,{...m,value:m.original_value}]) : Object.entries(r.conditions);
  const provenance = r.raw_cells[0]?.provenance;
  const caption = r.extra_metadata?.table_caption?.original_value;
  const source = state.sources.find(s => s.sha256 === provenance?.source_sha256 && s.available_locally);
  const documentLink = source ? `/api/documents/${encodeURIComponent(source.source_id)}${provenance?.page ? `#page=${provenance.page}` : ''}` : safeURL(provenance?.source_url);
  main.innerHTML = heading('EXPERIMENT BROWSER','Every value has a source.','Inspect the candidate mapping, compare original values, and record your review.') +
  filterControls() + `<div class="record-picker" role="group" aria-label="Select experiment">${records.map(record => `<button data-record="${esc(recordKey(record))}" class="${state.record===recordKey(record)?'active':''}" aria-pressed="${state.record===recordKey(record)}">${esc(record.identity.test_id)}</button>`).join('')}</div>
  <div class="record-grid"><div><section class="panel"><div class="record-head"><div><div class="eyebrow">${esc(names[r.identity.investigation_id] || r.identity.investigation_id)} / ${esc(r.identity.investigation_id)}</div><h2>Test ${esc(r.identity.test_id)}</h2><span class="muted" style="font-size:11px">${provenance?.page ? 'PDF table row · Background study' : `Sample ${esc(r.identity.sample_id || 'unknown')} · Individual run`}</span></div>${r.human_review_status==='unreviewed' ? tag('Human review open','amber') : tag('Reviewed extraction','green')}</div>
  ${caption ? `<div class="notice"><strong>Source caption</strong><p>${esc(caption)}</p>Background-study table; verify the original page and context.</div>` : ''}
  <div class="tabs" role="tablist" aria-label="Record fields">${[['conditions','Conditions'],['outcomes',provenance?.page ? 'Reported quantities' : 'Measured outcomes'],['settings','Instrument settings'],['raw','Original cells']].map(([id,t]) => `<button role="tab" id="tab-${id}" aria-selected="${state.tab===id}" aria-controls="record-fields" class="${state.tab===id?'active':''}" data-tab="${id}">${t}</button>`).join('')}</div>
  <div id="record-fields" role="tabpanel" aria-labelledby="tab-${state.tab}">${state.tab === 'raw' ? `<div class="table-scroll"><table><thead><tr><th>Original column</th><th>Original value</th></tr></thead><tbody>${r.raw_cells.map(c => `<tr><td>${esc(c.provenance.column)}</td><td class="mono">${c.original_value === '' || c.original_value == null ? '<span class="muted">Missing</span>' : esc(c.original_value)}</td></tr>`).join('')}</tbody></table></div>` : `<div class="field-grid">${fields.map(([name,m]) => `<div><div class="field-label">${esc(pretty(name))}</div><div class="field-value">${val(m)}</div><div class="field-raw">Source: “${esc(m.original_value ?? 'missing')}”${m.original_unit ? ` · ${esc(m.original_unit)}` : ''}${m.qualifier ? ` · ${esc(m.qualifier)}` : ''}</div></div>`).join('')}</div>`}</div>
  <div class="panel-footer"><span>Automated validation</span>${tag(pretty(r.validation_status),r.issues.length?'amber':'green')}</div></section>
  <section class="panel"><div class="panel-head"><h2>Source trail</h2><a class="btn small" href="${documentLink}" target="_blank" rel="noopener noreferrer">Open source ↗</a></div><div class="panel-body provenance">${esc(provenance?.file || 'No source')}<br>${provenance?.page ? `PDF page ${esc(provenance.page)} · Table ${esc(provenance.table)} · Row ${esc(provenance.row)}` : `Source record ${esc(provenance?.row ?? 'see source reference')} · Test ${esc(r.identity.test_id)}`}${provenance?.locator ? `<br>${esc(provenance.locator)}` : ''}<details><summary>File integrity and provenance</summary>SHA-256: ${esc(provenance?.source_sha256 || 'Unavailable')}<br>Original headers and values are retained in the Original cells tab.</details></div></section>
  ${notes.length ? `<section class="panel"><div class="panel-head"><h2>Review notes</h2>${tag(`${notes.length} saved`)}</div><div class="panel-body">${notes.slice().reverse().map(n => `<div class="draft-note"><strong>${esc(pretty(n.decision))}</strong><small>${esc(n.reviewer)} · ${esc(new Date(n.saved_at_utc).toLocaleString())} · Draft · ${esc(n.binding_status === 'matched' ? 'candidate matched' : n.binding_status === 'stale' ? 'candidate changed; review again' : 'candidate binding unverified')}</small><p>${esc(n.note)}</p><small>Source evidence: ${esc(n.evidence)}</small></div>`).join('')}</div></section>` : ''}</div>
  <aside><section class="panel"><div class="panel-head"><h2>Review flags</h2>${tag(r.issues.length,r.issues.length?'amber':'green')}</div><div class="panel-body">${r.issues.length ? r.issues.map(i => `<div class="issue"><strong>${esc(i.field)}</strong>${esc(i.message)}</div>`).join('') : '<p class="muted" style="font-size:12px;line-height:1.8">No automated flags. Scientific review is still required.</p>'}</div></section>
  <section class="panel"><div class="panel-head"><h2>Your review</h2>${tag('DRAFT')}</div><form id="review-form" class="panel-body review-form"><div class="form-field"><label for="reviewer">Reviewer</label><input id="reviewer" name="reviewer" required maxlength="120" placeholder="Your name" value="${esc(localStorage.getItem('atlas-reviewer') || '')}"></div><div class="form-field"><label for="decision">Assessment</label><select id="decision" name="decision"><option value="needs_research">Needs research</option><option value="accept_extraction">Extraction looks correct</option><option value="correction_proposed">Correction proposed</option></select></div><div class="form-field"><label for="note">Finding or question</label><textarea id="note" name="note" required minlength="3" maxlength="5000" placeholder="What did you confirm or find?"></textarea></div><div class="form-field"><label for="evidence">Supporting source</label><textarea id="evidence" name="evidence" required minlength="3" maxlength="2000" placeholder="Document, page, table or source URL" style="min-height:75px"></textarea></div><button class="btn primary full-width" type="submit">Save review note</button><p class="form-hint">Notes are saved locally for adjudication. Candidate values and gold-fixture approval are managed separately.</p><div id="review-error" role="alert"></div></form></section></aside></div>`;
  bindRecords();
  main.querySelectorAll('[data-tab]').forEach(btn => btn.addEventListener('click', () => { state.tab = btn.dataset.tab; renderExperiments(); }));
  bindFilters();
  const reviewForm = main.querySelector('#review-form');
  const draftKey = `${r.identity.investigation_id}/${r.identity.test_id}`;
  if (state.reviewDrafts[draftKey]) Object.entries(state.reviewDrafts[draftKey]).forEach(([name,value]) => { reviewForm.elements.namedItem(name).value=value; });
  reviewForm.addEventListener('input', () => { state.reviewDrafts[draftKey]=Object.fromEntries(new FormData(reviewForm)); });
  reviewForm.addEventListener('submit', async e => {
    e.preventDefault(); const form = e.currentTarget; const button = form.querySelector('button[type=submit]'); button.disabled = true;
    const fields = Object.fromEntries(new FormData(form));
    try { const saved = await api('/api/reviews', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...fields,test_id:r.identity.test_id,investigation_id:r.identity.investigation_id}) }); state.notes.push(saved); delete state.reviewDrafts[draftKey]; localStorage.setItem('atlas-reviewer',fields.reviewer); renderExperiments(); toast('Review note saved locally.'); }
    catch (err) { form.querySelector('#review-error').textContent = err.message; button.disabled = false; }
  });
}
function renderSources() {
  main.innerHTML = heading('SOURCE LIBRARY','A traceable foundation.','Browse the selected NASA files, their availability and captured versions.') + `<div class="filters"><input id="source-query" type="search" aria-label="Filter source files" placeholder="Filter by filename or investigation…" value="${esc(state.sourceFilter)}"><select id="source-status" aria-label="Filter by availability"><option value="">All availability</option>${['downloaded','indexed'].map(s => `<option value="${s}" ${state.sourceStatus===s?'selected':''}>${pretty(s)}</option>`).join('')}</select></div><div id="source-table"></div>`;
  renderSourceTable();
  main.querySelector('#source-query').addEventListener('input', e => { state.sourceFilter=e.target.value; renderSourceTable(); });
  main.querySelector('#source-status').addEventListener('change', e => { state.sourceStatus=e.target.value; renderSourceTable(); });
}
function renderSourceTable() {
  const rows = state.sources.filter(s => (!state.sourceStatus || s.status===state.sourceStatus) && `${s.file_name} ${s.investigation_ids.map(i => names[i]).join(' ')} ${s.investigation_ids}`.toLowerCase().includes(state.sourceFilter.toLowerCase()));
  document.querySelector('#source-table').innerHTML = `<section class="panel"><div class="panel-head"><h2>${rows.length} selected source files</h2>${tag(`${state.overview.files_failed} unavailable`,'amber')}</div>${rows.length ? `<div class="table-scroll"><table><thead><tr><th>Document / file</th><th>Investigation</th><th>Availability</th><th>Open</th></tr></thead><tbody>${rows.map(s => `<tr><td class="source-name"><strong>${esc(s.file_name)}</strong><small>${esc(s.category)} · ${esc(s.provider.toUpperCase())}${s.version!=null?` · File v${s.version}`:''}</small></td><td>${s.investigation_ids.map(i => `<div style="margin-bottom:4px">${esc(names[i] || i)}</div>`).join('')}</td><td>${tag(pretty(s.status),s.status==='downloaded'?'green':s.status==='failed'?'red':'')}<small>${esc(s.error || (s.sha256 ? 'Checksum captured' : ''))}</small></td><td>${s.available_locally ? `<a class="btn small" href="/api/documents/${encodeURIComponent(s.source_id)}" target="_blank" rel="noopener noreferrer">Open file ↗</a>` : `<a class="btn small" href="${safeURL(s.source_url)}" target="_blank" rel="noopener noreferrer">NASA ↗</a>`}</td></tr>`).join('')}</tbody></table></div>` : empty('No matching files','Try another filename or availability filter.')}<div class="panel-footer"><span>Source files referenced by candidate batches and indexed documents.</span></div></section>`;
}
function renderSearch() {
  const t = state.corpus?.totals || {};
  main.innerHTML = heading('ASK THE CORPUS','Ask NASA combustion research a question.','Get answers built only from the indexed reports, with every claim linked to the exact passage and page it came from.') +
  `<div class="notice"><strong>Searching ${count(t.documents)} document${t.documents===1?'':'s'} · ${count(t.pages)} pages · ${count(t.passages)} text passages · ${count(t.figures)} figures</strong><br>Answers quote the source verbatim. Figure descriptions are AI interpretations that have not been reviewed; check numbers against the original page. <a href="#corpus">See what is in the corpus →</a></div>
  <form id="search-form" class="search-box"><input id="question" name="question" type="search" maxlength="1000" required aria-label="Ask a question about the corpus" placeholder="Ask about materials, conditions, results or methods…" value="${esc(state.question)}"><select id="investigation" aria-label="Investigation scope">${optionList(state.investigation)}</select><button class="btn primary" type="submit" ${state.searching?'disabled':''}>${state.searching?'Searching…':'Ask'}</button></form>
  <div class="suggestions"><span>TRY</span>${['Which variables were tested in BASS-II?','How does opposed-flow velocity affect flame spread over thin PMMA?','Which components are labelled in Figure 5.1 of the BASS-II duct schematic?','What was the initial CO reading for BASS-II test O12?','Which FLEX tables report droplet extinction diameters?','How does adding helium to the atmosphere affect FLEX droplet flames?','What did the Saffire experiments show about flame spread on large samples?','How many samples were burned in BASS-II?','What flame spread rates were measured for titanium alloy at Martian surface pressure?'].map(q => `<button data-query="${esc(q)}" ${state.searching?'disabled':''}>${esc(q)}</button>`).join('')}</div>
  <details class="panel search-settings"><summary>Search settings</summary><div class="panel-body"><label>Search method <select id="search-method">${[['keyword','Keyword'],['dense','Semantic'],['hybrid','Hybrid (recommended)']].map(([v,t])=>`<option value="${v}" ${state.searchMethod===v?'selected':''}>${t}</option>`).join('')}</select></label> <label><input id="provider-calls" type="checkbox" ${state.allowProviderCalls?'checked':''}> Allow OpenAI calls for this query</label> <label><input id="generate-answer" type="checkbox" ${state.generateAnswer?'checked':''} ${state.ragStatus.answer_ready?'':'disabled'}> Generate cited answer</label><p class="form-hint">Semantic and hybrid search send the question to OpenAI; answers also send the retrieved passages. Answer model: ${esc(state.ragStatus.answer_model||'not configured')}.</p></div></details>
  <div id="search-results" aria-live="polite"></div>`;
  renderSearchResults();
  main.querySelectorAll('[data-support]').forEach(button => button.addEventListener('click', () => {
    const index=state.results.hits.findIndex(hit=>hit.chunk.chunk_id===button.dataset.support);
    main.querySelectorAll('.result-card')[index]?.scrollIntoView({behavior:'smooth',block:'start'});
  }));
  main.querySelector('#search-form').addEventListener('submit', e => { e.preventDefault(); runSearch(); });
  main.querySelectorAll('[data-query]').forEach(btn => btn.addEventListener('click', () => { main.querySelector('#question').value=btn.dataset.query; runSearch(); }));
}
async function runSearch() {
  if(state.searching) return;
  state.question = main.querySelector('#question').value.trim(); state.investigation=main.querySelector('#investigation').value;
  state.searchMethod=main.querySelector('#search-method').value;
  state.allowProviderCalls=main.querySelector('#provider-calls').checked;
  state.generateAnswer=main.querySelector('#generate-answer').checked;
  if (!state.question) return;
  state.searching=true; state.progress=[]; renderSearch();
  try { const payload=await askStream({question:state.question, investigation:state.investigation || null, method:state.searchMethod, generate_answer:state.generateAnswer, allow_provider_calls:state.allowProviderCalls});
    state.results={question:payload.question,method:payload.method,answer:payload.answer,hits:payload.results.map(c=>({chunk:{...c,
      title:c.filename,page:c.physical_page,file_name:c.filename,investigation_ids:c.investigation_id?[c.investigation_id]:[],
      extraction_method:c.visual?'derived_visual_text':'pdf_native_text',warnings:c.visual?[`Derived ${c.visual.kind}: ${c.visual.method}; ${c.visual.review_status}. Verify against the original crop.`]:[]}}))}; }
  catch(err) { state.results={error:err.message}; }
  state.searching=false; if(['ask','search'].includes(route())) renderSearch();
}
function renderSearchResults() {
  const el=document.querySelector('#search-results'); const result=state.results;
  if(state.searching) { el.innerHTML=progressHTML(); return; }
  if(!result) { el.innerHTML=empty('A source is a good place to start.',`${count(state.overview.chunks)} passages from ${state.overview.documents} documents, with page-level citations.`); return; }
  if(result.error) { el.innerHTML=stepsSummaryHTML(true)+`<div class="error" role="alert">${esc(result.error)}</div>`; return; }
  if(!result.hits.length) { el.innerHTML=empty('No matching passages.','Try different terms or a broader investigation scope. This search provides no supported answer.'); return; }
  const answer=result.answer;
  const answerHTML=answer ? `<section class="panel"><div class="panel-body"><h2>${answer.status==='answered'?'Answer from retrieved evidence':'Insufficient evidence'}</h2>${answer.claims.map(claim=>`<div class="draft-note"><p>${esc(String(claim.text).replace(LABEL_PREFIX,''))}</p>${groupSupports(claim.supports).map(([first,...rest])=>`<blockquote>${esc(first.quote)}</blockquote><button class="btn link" data-support="${esc(first.chunk_id)}">View supporting passage →</button>${rest.length?`<small class="form-hint" style="display:block">Also stated in ${rest.length} other passage${rest.length===1?'':'s'}: ${rest.map(s=>`<button class="btn link" data-support="${esc(s.chunk_id)}">${esc(s.chunk_id.split(':').slice(1,2).join('') || 'passage')}</button>`).join(' · ')}</small>`:''}`).join('')}</div>`).join('')}${answer.limitations.map(l=>`<p class="form-hint">${esc(l)}</p>`).join('')}${answer.status==='answered'?'<p class="form-hint">Citation and excerpt checks passed. Scientific support still requires source verification.</p>':'<p class="form-hint">No claim was supported by the retrieved passages. This means missing from the indexed collection, not unstudied.</p>'}</div></section>` : '';
  el.innerHTML=stepsSummaryHTML() + answerHTML + `<div class="results-meta"><span>${result.hits.length} passages for “${esc(result.question)}”</span><span>${esc(pretty(result.method || 'keyword'))} retrieval · Original excerpts</span></div>` + result.hits.map((hit,i) => {
    const c=hit.chunk; const source=state.sources.find(s=>s.source_id===c.source_id);
    const link=source?.available_locally ? `/api/documents/${encodeURIComponent(c.source_id)}#page=${c.page}` : safeURL(c.file_url || c.source_url);
    return `<article class="result-card"><div class="result-top"><span class="eyebrow" style="margin:0">PASSAGE ${String(i+1).padStart(2,'0')} · ${esc(c.investigation_ids.map(i=>names[i]||i).join(' / '))}</span>${(c.record_card ? `${tag(`Table record · ${c.record_card.review_action}`,'green')} ${tag(c.record_card.locator || 'CSV record')}` : tag(`Page ${c.page}`))}</div><h2>${esc(c.title)}</h2>${c.section?`<span class="muted" style="font-size:11px">Section hint: ${esc(c.section)}</span>`:''}<div class="excerpt">${esc(c.text)}</div><div class="result-footer"><span>${esc(source?.category || 'Document')} · ${esc(c.extraction_method==='pdf_native_text'?'Native PDF text':c.extraction_method==='derived_visual_text'?'Derived visual text (not source text)':'Plain text')}</span><a class="btn small" href="${link}" target="_blank" rel="noopener noreferrer">Open cited page ↗</a></div><details><summary>Source details and extraction notes</summary><p><a href="${safeURL(c.source_url)}" target="_blank" rel="noopener noreferrer">Source record ↗</a></p>Chunk: ${esc(c.chunk_id)}<br>SHA-256: ${esc(c.sha256)}${c.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details></article>`;
  }).join('');
  el.querySelectorAll('.result-card').forEach((card,index)=>{
    const chunk=result.hits[index].chunk;
    if(!chunk.visual || !chunk.crop_url?.startsWith('/api/visuals/')) return;
    const note=document.createElement('p');
    note.className='notice';
    note.textContent=`${pretty(chunk.visual.kind)} ${chunk.visual.label} · ${pretty(chunk.visual.review_status)} · Derived visual evidence; inspect the original page.`;
    const details=document.createElement('details');
    const summary=document.createElement('summary');
    summary.textContent='View original visual crop';
    const image=document.createElement('img');
    image.src=chunk.crop_url; image.loading='lazy'; image.style.maxWidth='100%';
    image.alt=`Original page crop for ${chunk.visual.kind} ${chunk.visual.label}`;
    details.append(summary,image); card.prepend(note); card.append(details);
    if(chunk.visual.kind==='table') renderTableCells(card, chunk);
  });
}
async function renderTableCells(card, chunk) {
  // Show the structured cells as a grid; the serialized JSON excerpt is only for retrieval.
  const excerpt=card.querySelector('.excerpt');
  try {
    const data=await api(chunk.crop_url+'/cells');
    const t=data.table; const byRow=new Map();
    t.cells.slice().sort((a,b)=>a.row-b.row||a.column-b.column).forEach(cell=>{ if(!byRow.has(cell.row)) byRow.set(cell.row,[]); byRow.get(cell.row).push(cell); });
    const rows=[...Array(t.rows).keys()].map(r=>`<tr>${(byRow.get(r)||[]).map(cell=>{
      const tagName=cell.role==='data'?'td':'th'; const span=`${cell.row_span>1?` rowspan="${cell.row_span}"`:''}${cell.column_span>1?` colspan="${cell.column_span}"`:''}`;
      const value=cell.state==='unreadable'?'<em>unreadable</em>':cell.state==='blank'?'<em>blank</em>':esc(cell.text);
      const unit=cell.unit&&cell.role==='data'?` <small>${esc(cell.unit)}</small>`:'';
      const title=cell.uncertainty?` title="${esc(cell.uncertainty)}"`:'';
      return `<${tagName}${span}${title}${cell.role==='row_header'?' scope="row"':''}>${value}${unit}</${tagName}>`; }).join('')}</tr>`).join('');
    const wrap=document.createElement('div'); wrap.className='table-scroll';
    wrap.innerHTML=`<table class="source-table"><caption>${esc(`Table ${data.label}: ${data.caption}`)} · ${esc(pretty(data.review_status))} transcription</caption>${rows}</table>${t.footnotes.length?`<ul class="form-hint">${t.footnotes.map(f=>`<li>${esc(f)}</li>`).join('')}</ul>`:''}`;
    excerpt?.replaceWith(wrap);
  } catch(err) { /* Keep the serialized excerpt when structured cells are unavailable. */ }
}
async function start() {
  try {
    const [overview, experiments, sources] = await Promise.all([api('/api/overview'),api('/api/experiments'),api('/api/sources')]);
    state.ragStatus=await api('/api/rag-status');
    try { state.corpus=await api('/api/corpus'); } catch { state.corpus=null; }
    try { const me=await api('/api/me'); const slot=document.querySelector('#ui-switch-slot'); if(slot){ slot.innerHTML=uiSwitchHTML(me,'workspace'); bindUiSwitch(slot); } } catch { /* switch is optional */ }
    state.searchMethod=state.ragStatus.semantic_ready?'hybrid':'keyword';
    state.generateAnswer=state.ragStatus.answer_ready;
    state.allowProviderCalls=state.ragStatus.semantic_ready || state.ragStatus.answer_ready;
    if(sources.sources.length && sources.sources.every(s=>s.investigation_ids.length===1 && s.investigation_ids[0]==='PSI-25')) state.investigation='PSI-25';
    state.recordSources=experiments.record_sources; state.overview=overview; state.preservedRecords=experiments.preserved_records || []; state.records=[...experiments.records.map(presentRecord),...state.preservedRecords]; state.mappings=experiments.mappings; state.notes=experiments.notes; state.sources=sources.sources;
    document.querySelector('#nav-count').textContent=overview.experiments;
    if(overview.demo) document.querySelector('.stage').textContent='SYNTHETIC DEMO';
    render();
  } catch(err) { main.innerHTML=`<div class="error" role="alert">The workspace could not be loaded. ${esc(err.message)}</div><button class="btn" id="retry" style="margin-top:15px">Try again</button>`; main.querySelector('#retry').addEventListener('click',start); }
}
window.addEventListener('hashchange',()=>{ if(location.hash==='#main') { main.focus(); return; } if(state.overview) render(); });

// ---- Shared helpers for user-facing pages ----
const pageLink = (sourceId, page) => {
  const src = state.sources.find(s => s.source_id === sourceId);
  return src?.available_locally ? `/api/documents/${encodeURIComponent(sourceId)}#page=${page}` : safeURL(src?.source_url);
};
const shortSection = s => String(s || 'Unsectioned').replace('Individual Principal Investigator Report: ', 'PI report: ').replace('Project Scientist Report: ', 'Project scientist: ').replace(/^1\.0 Summary of .*/, '1.0 Summary');
async function refreshCorpus() {
  [state.corpus, state.ragStatus] = await Promise.all([api('/api/corpus'), api('/api/rag-status')]);
  state.topicMap = null;
}

// ---- Corpus page ----
function renderCorpus() {
  const c = state.corpus;
  if (!c) { main.innerHTML = '<div class="loading">Loading the corpus…</div>'; refreshCorpus().then(() => route() === 'corpus' && renderCorpus()).catch(e => { main.innerHTML = `<div class="error" role="alert">${esc(e.message)}</div>`; }); return; }
  const t = c.totals;
  const stat = (label, value, foot) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-number">${count(value)}</div><div class="stat-foot">${foot}</div></div>`;
  const known = [...new Set(c.documents.flatMap(d => d.investigation_ids))];
  main.innerHTML = heading('CORPUS', 'What the atlas can draw on.', 'Every indexed document, page and figure, where each topic sits, and a way to add new reports.') +
  `<div class="stats">${stat('Documents', t.documents, `${count(t.investigations)} investigation${t.investigations === 1 ? '' : 's'}`)}${stat('Pages', t.pages, 'physical PDF pages')}${stat('Text passages', t.passages, `${count(t.embedded)} with semantic search`)}${stat('Figures & tables', t.figures + t.tables, `${count(t.figures)} figures · ${count(t.tables)} tables`)}</div>
  <section class="panel"><div class="panel-head"><div><h2>Topic map</h2><p>Each mark is a text passage (●) or figure description (◆). Marks close together discuss similar topics. Position comes from the embeddings; the axes have no units or scientific meaning.</p></div></div>
    <div class="panel-body"><div class="section-filter" role="group" aria-label="Highlight a report section"></div><div class="map-wrap"><svg id="topic-map" viewBox="0 0 800 420" role="img" aria-label="Topic map of corpus passages"></svg><div id="map-tip" class="map-tip" hidden></div></div><div id="map-detail" class="map-detail form-hint">Hover a mark for its page and topic; click it to open the passage.</div></div></section>
  <section class="panel"><div class="panel-head"><div><h2>Documents</h2><p>Bar height shows how much text each page has; orange marks show figures. Click a page to open it.</p></div></div><div class="panel-body">${c.documents.length ? c.documents.map(renderDocument).join('') : empty('No documents yet', 'Add a PDF below to start building the corpus.')}</div></section>
  <section class="panel"><div class="panel-head"><div><h2>Add a document</h2><p>Upload a NASA report or paper (PDF). Text is extracted page by page and added without changing existing documents.</p></div></div>
    <form id="upload-form" class="panel-body upload-form">
      <div class="form-field"><label for="upload-file">PDF file (up to 80 MB)</label><input id="upload-file" type="file" accept="application/pdf,.pdf" required></div>
      <div class="form-field"><label for="upload-investigation">Investigation ID</label><input id="upload-investigation" list="known-investigations" required maxlength="79" placeholder="e.g. PSI-25 or SAFFIRE-II"><datalist id="known-investigations">${known.map(i => `<option value="${esc(i)}">${esc(names[i] || i)}</option>`).join('')}</datalist></div>
      <div class="form-field"><label for="upload-url">Source URL (optional)</label><input id="upload-url" type="url" placeholder="https://ntrs.nasa.gov/citations/…"></div>
      <label><input id="upload-embed" type="checkbox" ${state.ragStatus.semantic_ready ? 'checked' : ''}> Enable semantic search (creates vector embeddings so passages can be found by meaning, not just keywords)</label>
      <button class="btn primary" type="submit">Add to corpus</button>
      <p class="form-hint">Figures are not described automatically yet; text search and cited answers work immediately. Scanned PDFs without a text layer will index as sparse pages.</p>
      <div id="upload-status" aria-live="polite"></div>
    </form></section>`;
  bindUpload();
  drawTopicMap();
}
function renderDocument(doc) {
  const max = Math.max(1, ...doc.page_strip.map(p => p.words));
  const sections = [];
  doc.page_strip.forEach(p => { const last = sections[sections.length - 1]; if (!last || last.name !== p.section) sections.push({ name: p.section, first: p.page, last: p.page, figures: p.figures.length }); else { last.last = p.page; last.figures += p.figures.length; } });
  const bars = doc.page_strip.map((p, i) => {
    const start = i > 0 && doc.page_strip[i - 1].section !== p.section;
    const h = p.sparse ? 4 : Math.max(6, Math.round(100 * p.words / max));
    const tip = `Page ${p.page} · ${shortSection(p.section)} · ${p.words} words${p.figures.length ? ` · Figure ${p.figures.join(', ')}` : ''}${p.tables.length ? ` · Table ${p.tables.join(', ')}` : ''}`;
    return `<a class="strip-page${start ? ' section-start' : ''}${p.sparse ? ' sparse' : ''}" href="${pageLink(doc.source_id, p.page)}" target="_blank" rel="noopener noreferrer" title="${esc(tip)}" aria-label="${esc(tip)}"><span style="height:${h}%"></span>${p.figures.length || p.tables.length ? '<i></i>' : ''}</a>`;
  }).join('');
  return `<article class="doc-card"><div class="doc-head"><div><h3>${esc(doc.filename)}</h3><div>${doc.investigation_ids.map(i => tag(names[i] ? `${names[i]} · ${i}` : i)).join(' ')}</div></div><div class="doc-actions"><a class="btn small" href="${pageLink(doc.source_id, 1)}" target="_blank" rel="noopener noreferrer">Open PDF ↗</a>${doc.source_url ? `<a class="btn small" href="${safeURL(doc.source_url)}" target="_blank" rel="noopener noreferrer">Source record ↗</a>` : ''}</div></div>
    <p class="form-hint">${count(doc.pages)} pages · ${count(doc.passages)} passages · ${count(doc.figures)} figures · ${count(doc.tables)} tables · ${count(doc.embedded)} embedded</p>
    <div class="strip" role="group" aria-label="Pages of ${esc(doc.filename)}">${bars}</div>
    <details><summary>Sections (${sections.length})</summary><div class="table-scroll"><table><thead><tr><th>Section</th><th>Pages</th><th>Figures</th></tr></thead><tbody>${sections.map(s => `<tr><td>${esc(shortSection(s.name))}</td><td><a href="${pageLink(doc.source_id, s.first)}" target="_blank" rel="noopener noreferrer">${s.first}–${s.last}</a></td><td>${s.figures}</td></tr>`).join('')}</tbody></table></div></details></article>`;
}
async function drawTopicMap() {
  const svg = main.querySelector('#topic-map'); if (!svg) return;
  try { state.topicMap ||= await api('/api/corpus/map'); } catch (err) { svg.outerHTML = `<div class="error">${esc(err.message)}</div>`; return; }
  if (route() !== 'corpus') return;
  const points = state.topicMap.points || [];
  if (!points.length) { svg.outerHTML = empty('No embeddings yet', 'Enable semantic search for documents to see the topic map.'); return; }
  const sections = []; const seen = new Map();
  [...points].sort((a, b) => a.page - b.page).forEach(p => { const key = `${p.filename} · ${p.section}`; if (!seen.has(key)) { seen.set(key, 0); sections.push(key); } seen.set(key, seen.get(key) + 1); });
  const multiDoc = new Set(points.map(p => p.source_id)).size > 1;
  const label = key => multiDoc ? key : shortSection(key.split(' · ').slice(1).join(' · '));
  const filter = main.querySelector('.section-filter');
  filter.innerHTML = `<span class="eyebrow" style="margin:0 6px 0 0">HIGHLIGHT</span><button data-section="" class="${!state.mapSection ? 'active' : ''}">All</button>` + sections.map(s => `<button data-section="${esc(s)}" class="${state.mapSection === s ? 'active' : ''}">${esc(label(s))} <small>${seen.get(s)}</small></button>`).join('');
  filter.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { state.mapSection = b.dataset.section; drawTopicMap(); }));
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = x => 24 + (x - x0) / ((x1 - x0) || 1) * 752, sy = y => 396 - (y - y0) / ((y1 - y0) || 1) * 372;
  const on = p => !state.mapSection || `${p.filename} · ${p.section}` === state.mapSection;
  const ordered = [...points].sort((a, b) => on(a) - on(b));
  const mark = (p, i) => {
    const x = sx(p.x).toFixed(1), y = sy(p.y).toFixed(1), cls = `mark ${on(p) ? (state.mapSection ? 'hi' : 'all') : 'dim'}`;
    const shape = p.kind === 'text' ? `<circle class="${cls}" cx="${x}" cy="${y}" r="4.5"/>` : `<rect class="${cls}" x="${x - 5}" y="${y - 5}" width="10" height="10" transform="rotate(45 ${x} ${y})"/>`;
    return `<g class="hit" data-i="${points.indexOf(p)}" tabindex="0">${shape}<circle cx="${x}" cy="${y}" r="10" fill="transparent"/></g>`;
  };
  svg.innerHTML = `<rect x="0.5" y="0.5" width="799" height="419" rx="6" class="map-frame"/>` + ordered.map(mark).join('');
  const tip = main.querySelector('#map-tip'), detail = main.querySelector('#map-detail');
  const describe = p => `<strong>${esc(p.label || 'Passage')} · page ${p.page}</strong><br><span>${esc(shortSection(p.section))}${multiDoc ? ` · ${esc(p.filename)}` : ''}</span><br>${esc(p.snippet)}${p.snippet.length >= 220 ? '…' : ''}`;
  svg.querySelectorAll('.hit').forEach(g => {
    const p = points[Number(g.dataset.i)];
    const show = e => { const box = svg.getBoundingClientRect(); tip.innerHTML = describe(p); tip.hidden = false; const cx = (e.clientX ?? box.left + sx(p.x) / 800 * box.width) - box.left, cy = (e.clientY ?? box.top + sy(p.y) / 420 * box.height) - box.top; tip.style.left = `${Math.min(cx + 14, box.width - 300)}px`; tip.style.top = `${cy + 14}px`; };
    g.addEventListener('mousemove', show); g.addEventListener('focus', show);
    g.addEventListener('mouseleave', () => { tip.hidden = true; }); g.addEventListener('blur', () => { tip.hidden = true; });
    const open = () => { detail.innerHTML = `${describe(p)}<div style="margin-top:10px;display:flex;gap:8px"><a class="btn small" href="${pageLink(p.source_id, p.page)}" target="_blank" rel="noopener noreferrer">Open page ${p.page} ↗</a></div>`; };
    g.addEventListener('click', open); g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  });
}
function bindUpload() {
  const form = main.querySelector('#upload-form'); if (!form) return;
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const file = form.querySelector('#upload-file').files[0], status = form.querySelector('#upload-status'), button = form.querySelector('button[type=submit]');
    if (!file) return;
    if (file.size > 80 * 1024 * 1024) { status.innerHTML = '<div class="error">The PDF is larger than 80 MB.</div>'; return; }
    const params = new URLSearchParams({ filename: file.name, investigation: form.querySelector('#upload-investigation').value.trim(), source_url: form.querySelector('#upload-url').value.trim(), embed: form.querySelector('#upload-embed').checked ? '1' : '0' });
    button.disabled = true; status.innerHTML = '<div class="loading" style="padding:20px">Extracting and indexing pages… large reports can take a minute.</div>';
    try {
      const r = await api(`/api/upload?${params}`, { method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file });
      await refreshCorpus(); state.sources = (await api('/api/sources')).sources;
      toast(r.status === 'unchanged' ? 'That document is already in the corpus.' : `Added ${r.filename}: ${r.physical_pages} pages, ${r.chunks_added} passages.`);
      if (route() === 'corpus') renderCorpus();
      const s2 = main.querySelector('#upload-status');
      if (s2) s2.innerHTML = `<div class="notice">${r.status === 'unchanged' ? 'Already indexed — nothing changed.' : `Added <strong>${esc(r.filename)}</strong> (${esc(r.investigation_id)}): ${count(r.physical_pages)} pages, ${count(r.chunks_added)} passages, ${count(r.embedded_chunks)} embedded${r.sparse_pages ? `, ${count(r.sparse_pages)} sparse pages (possibly scanned)` : ''}.`}</div>`;
    } catch (err) { status.innerHTML = `<div class="error" role="alert">${esc(err.message)}</div>`; button.disabled = false; }
  });
}

// ---- Research directions page ----
state.directions = { topic: '', result: null, loading: false, error: '' };
function renderDirections() {
  const d = state.directions;
  main.innerHTML = heading('RESEARCH DIRECTIONS', 'Plan the next experiment from the evidence.', 'Describe a topic or proposed test condition. The atlas gathers what the corpus reports, what the authors say is still open, what the collection does not cover, and suggests next steps tied to those citations.') +
  `<div class="notice"><strong>Suggestions are starting points for expert judgment, not validated recommendations or predictions.</strong> Each one cites the passages it builds on. “Not found” means not found in this indexed collection, not that it has never been studied.</div>
  <form id="directions-form" class="panel panel-body"><label for="topic">Topic or proposed condition</label><textarea id="topic" rows="3" maxlength="1000" required placeholder="e.g. Flame spread over thin PMMA at low opposed-flow velocity and reduced oxygen">${esc(d.topic)}</textarea>
    <div class="filters" style="margin:14px 0 0"><select id="directions-investigation" aria-label="Investigation scope">${optionList(state.investigation)}</select><button class="btn primary" type="submit" ${d.loading || !state.ragStatus.answer_ready ? 'disabled' : ''}>${d.loading ? 'Analyzing evidence…' : 'Find research directions'}</button></div>
    <p class="form-hint">Sends the topic and retrieved passages to OpenAI (${esc(state.ragStatus.answer_model || 'no model configured')}). Takes up to a minute.</p></form>
  <div class="suggestions"><span>TRY</span>${['Flame spread over thin PMMA at low opposed-flow velocity and reduced oxygen', 'Flammability limits of PMMA rods in microgravity', 'Concurrent-flow flame spread over cotton-fiberglass fabric'].map(q => `<button data-topic="${esc(q)}" ${d.loading ? 'disabled' : ''}>${esc(q)}</button>`).join('')}</div>
  <div id="directions-results" aria-live="polite">${renderDirectionsResult()}</div>`;
  main.querySelector('#directions-form').addEventListener('submit', e => { e.preventDefault(); runDirections(main.querySelector('#topic').value.trim()); });
  main.querySelectorAll('[data-topic]').forEach(b => b.addEventListener('click', () => runDirections(b.dataset.topic)));
}
async function runDirections(topic) {
  if (!topic || state.directions.loading) return;
  state.investigation = main.querySelector('#directions-investigation')?.value || state.investigation;
  Object.assign(state.directions, { topic, loading: true, error: '', result: null }); renderDirections();
  try { state.directions.result = await api('/api/directions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic, investigation: state.investigation || null, allow_provider_calls: true }) }); }
  catch (err) { state.directions.error = err.message; }
  state.directions.loading = false; if (route() === 'directions') renderDirections();
}
function renderDirectionsResult() {
  const d = state.directions;
  if (d.loading) return '<div class="loading">Reading the evidence and drafting directions…</div>';
  if (d.error) return `<div class="error" role="alert">${esc(d.error)}</div>`;
  if (!d.result) return '';
  const r = d.result.directions, byId = Object.fromEntries(d.result.results.map(x => [x.chunk_id, x]));
  if (r.status !== 'answered') return empty('Not enough evidence in the corpus', (r.gaps || [])[0] || 'No passages address this topic.');
  const claims = [...r.evidence, ...r.open_questions];
  const claimHTML = (c, i) => `<li id="dir-claim-${i}" class="draft-note"><span class="ref">[${i + 1}]</span> ${esc(c.text)}${c.supports.map(s => { const src = byId[s.chunk_id] || {}; return `<blockquote>${esc(s.quote)}</blockquote><small>${src.visual ? `${esc(pretty(src.visual.kind))} ${esc(src.visual.label)} · unreviewed AI description · ` : ''}<a href="${pageLink(src.source_id, src.physical_page)}" target="_blank" rel="noopener noreferrer">${esc(src.filename || 'Source')}, page ${esc(src.physical_page)} ↗</a></small>`; }).join('')}</li>`;
  const section = (title, hint, body) => `<section class="panel"><div class="panel-head"><div><h2>${title}</h2><p>${hint}</p></div></div><div class="panel-body">${body}</div></section>`;
  return section('What the corpus shows', 'Reported conditions, observations and conclusions, quoted from the source.', r.evidence.length ? `<ol class="claim-list">${r.evidence.map((c, i) => claimHTML(c, i)).join('')}</ol>` : '<p class="form-hint">No direct findings retrieved.</p>') +
    section('Open questions stated by the authors', 'Limitations, uncertainties and future work in the authors’ own words.', r.open_questions.length ? `<ol class="claim-list">${r.open_questions.map((c, i) => claimHTML(c, i + r.evidence.length)).join('')}</ol>` : '<p class="form-hint">The retrieved passages do not state open questions on this topic.</p>') +
    section('Not found in the indexed collection', 'Aspects of the topic the retrieved passages do not cover.', r.gaps.length ? `<ul class="gap-list">${r.gaps.map(g => `<li>${esc(g)}</li>`).join('')}</ul>` : '<p class="form-hint">No gaps identified in the retrieved passages.</p>') +
    section('Suggested next steps', 'AI-drafted from the cited items above. Review before acting on them.', r.suggestions.length ? r.suggestions.map(s => `<div class="suggestion-card">${tag(pretty(s.kind), s.kind === 'experiment' ? 'amber' : s.kind === 'analysis' ? 'green' : '')}<p>${esc(s.text)}</p><small>Based on ${s.basis.map(i => `<a href="#directions" data-claim="${i}">[${i + 1}]</a>`).join(' ')}</small></div>`).join('') : '<p class="form-hint">No suggestions could be grounded in the retrieved evidence.</p>') +
    `<p class="form-hint">${claims.length} cited items from ${d.result.results.length} retrieved passages.</p>`;
}
document.addEventListener('click', e => { const a = e.target.closest('[data-claim]'); if (!a) return; e.preventDefault(); document.querySelector(`#dir-claim-${a.dataset.claim}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); });
// ---- Streaming answers: progress events, then the result ----
state.progress = [];
function progressHTML() {
  const steps = state.progress;
  const last = steps[steps.length - 1];
  return `<section class="panel progress-panel" aria-live="polite"><div class="panel-body"><h2>${esc(last ? last.message : 'Starting…')}</h2><ol class="progress-steps">${steps.map((s, i) => `<li class="${i === steps.length - 1 ? 'current' : 'done'}"><span>${esc(s.message)}</span><small>${Number(s.elapsed_s || 0).toFixed(1)} s</small></li>`).join('')}</ol></div></section>`;
}
// After the answer arrives, keep the steps as a collapsed summary above it.
function stepsSummaryHTML(failed = false) {
  const steps = state.progress || [];
  if (!steps.length) return '';
  const total = Number(steps[steps.length - 1].elapsed_s || 0).toFixed(1);
  return `<details class="panel steps-summary"><summary><span>${failed ? '⚠ Stopped' : '✓ Answered'} in ${total} s</span><small>${steps.length} step${steps.length === 1 ? '' : 's'}</small></summary><ol class="progress-steps">${steps.map(s => `<li class="done"><span>${esc(s.message)}</span><small>${Number(s.elapsed_s || 0).toFixed(1)} s</small></li>`).join('')}</ol></details>`;
}
function showProgress(event) {
  state.progress.push(event);
  const el = document.querySelector('#search-results');
  if (el && state.searching) el.innerHTML = progressHTML();
}
async function askStream(body) {
  const response = await fetch('/api/ask/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (response.status === 404 || !response.body) return api('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) { const err = await response.json().catch(() => ({})); throw new Error(err.error || 'The request could not be completed.'); }
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '', result = null;
  const handle = line => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === 'progress') showProgress(event);
    else if (event.type === 'error') throw new Error(event.error);
    else if (event.type === 'result') result = event;
  };
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split('\n'); buffer = lines.pop();
    lines.forEach(handle);
    if (done) { handle(buffer); break; }
  }
  if (!result) throw new Error('The answer stream ended early. Please try again.');
  return result;
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
// ---- Answer display: strip label prefixes, group near-duplicate quotes ----
const LABEL_PREFIX = /^\s*(?:structured\s+)?(?:document|table(?:\s+record)?|record|figure|visual)(?:\s+description)?\s+evidence\s*[:\-–—]\s*/i;
function groupSupports(supports) {
  const tokens = t => new Set(String(t).toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(w => w.length > 2));
  const similar = (a, b) => { const x = tokens(a), y = tokens(b); if (!x.size || !y.size) return false; let n = 0; x.forEach(w => { if (y.has(w)) n += 1; }); return n / (x.size + y.size - n) >= 0.6; };
  const groups = [];
  supports.forEach(s => { const g = groups.find(group => similar(group[0].quote, s.quote)); if (g) g.push(s); else groups.push([s]); });
  return groups;
}
start();
