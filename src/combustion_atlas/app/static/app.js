const main = document.querySelector('#main');
const state = { overview: null, records: [], mappings: [], notes: [], sources: [], record: 'B1', tab: 'conditions', sourceFilter: '', sourceStatus: '', question: '', investigation: '', results: null, searching: false };
const names = { 'PSI-25': 'BASS-II', 'PSI-69': 'FLEX', 'PSI-98': 'Saffire I', 'PSI-99': 'Saffire II', 'PSI-100': 'Saffire III' };
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
const optionList = selected => `<option value="">All investigations</option>${Object.entries(state.overview?.demo ? Object.fromEntries(state.sources.flatMap(s=>s.investigation_ids).map(id=>[id,id])) : names).map(([id, name]) => `<option value="${id}" ${selected === id ? 'selected' : ''}>${name} · ${id}</option>`).join('')}`;
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
function route() { return location.hash.slice(1).split('/')[0] || 'overview'; }
function render() {
  const page = route();
  document.querySelectorAll('[data-nav]').forEach(link => { link.classList.toggle('active', link.dataset.nav === page); if (link.dataset.nav === page) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); });
  document.querySelector('#breadcrumb').innerHTML = `Workspace <span>/</span> ${esc({overview:'Overview',experiments:'Experiments',search:'Document search',sources:'Source library'}[page] || 'Overview')}`;
  if(page==='conditions') document.querySelector('#breadcrumb').textContent='Workspace / Proposed conditions';
  if(page==='search') document.querySelector('#breadcrumb').textContent='Workspace / Ask the evidence';
  ({ overview: renderOverview, experiments: renderExperiments, search: renderSearch, sources: renderSources, conditions: renderConditions }[page] || renderOverview)();
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
  main.innerHTML = heading('ASK THE EVIDENCE','Find the context behind the data.','Ask about past experiments and follow the evidence back to its original page.') +
  `<div class="notice"><strong>Local RAG POC · ${count(state.ragStatus.embedded_chunks)} embedded passages</strong><br>Currently testing the BASS-II Summary Report. This POC searches extracted text; dedicated table and figure extraction is still pending.</div>
  <form id="search-form" class="search-box"><input id="question" name="question" type="search" maxlength="1000" required aria-label="Search document passages" placeholder="Which variables were tested in BASS-II?" value="${esc(state.question)}"><select id="investigation" aria-label="Investigation scope">${optionList(state.investigation)}</select><button class="btn primary" type="submit" ${state.searching?'disabled':''}>${state.searching?'Searching…':'Ask the evidence'}</button></form>
  <div class="panel panel-body"><label>Search method <select id="search-method">${[['keyword','Keyword'],['dense','Semantic'],['hybrid','Hybrid']].map(([v,t])=>`<option value="${v}" ${state.searchMethod===v?'selected':''}>${t}</option>`).join('')}</select></label> <label><input id="provider-calls" type="checkbox" ${state.allowProviderCalls?'checked':''}> Allow OpenAI calls for this query</label> <label><input id="generate-answer" type="checkbox" ${state.generateAnswer?'checked':''} ${state.ragStatus.answer_ready?'':'disabled'}> Generate cited answer</label><p class="form-hint">Semantic and hybrid search send the question to OpenAI. Answer generation also sends retrieved passages. ${state.ragStatus.answer_ready?'Answer generation is configured.':'Answer generation needs an answer provider and model configured locally.'}</p></div>
  <div class="suggestions"><span>TRY A QUESTION</span>${['Which variables were tested in BASS-II?','How many tests were conducted in BASS-II?','What measured flame spread rates does this report give for titanium alloy samples at Martian surface pressure?'].map(q => `<button data-query="${q}" ${state.searching?'disabled':''}>${q}</button>`).join('')}</div><div class="notice">Document evidence is separate from candidate record approval. Generated claims include supporting excerpts; verify their meaning and numerical accuracy against the source.</div><div id="search-results" aria-live="polite"></div>`;
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
  state.searching=true; renderSearch();
  try { const payload=await api('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:state.question, investigation:state.investigation || null, method:state.searchMethod, generate_answer:state.generateAnswer, allow_provider_calls:state.allowProviderCalls})});
    state.results={question:payload.question,method:payload.method,answer:payload.answer,hits:payload.results.map(c=>({chunk:{...c,
      title:c.filename,page:c.physical_page,file_name:c.filename,investigation_ids:c.investigation_id?[c.investigation_id]:[],
      extraction_method:c.visual?'derived_visual_text':'pdf_native_text',warnings:c.visual?[`Derived ${c.visual.kind}: ${c.visual.method}; ${c.visual.review_status}. Verify against the original crop.`]:[]}}))}; }
  catch(err) { state.results={error:err.message}; }
  state.searching=false; if(route()==='search') renderSearch();
}
function renderSearchResults() {
  const el=document.querySelector('#search-results'); const result=state.results;
  if(state.searching) { el.innerHTML='<div class="loading">Finding passages in your local corpus…</div>'; return; }
  if(!result) { el.innerHTML=empty('A source is a good place to start.',`${count(state.overview.chunks)} passages from ${state.overview.documents} documents, with page-level citations.`); return; }
  if(result.error) { el.innerHTML=`<div class="error" role="alert">${esc(result.error)}</div>`; return; }
  if(!result.hits.length) { el.innerHTML=empty('No matching passages.','Try different terms or a broader investigation scope. This search provides no supported answer.'); return; }
  const answer=result.answer;
  const answerHTML=answer ? `<section class="panel"><div class="panel-body"><h2>${answer.status==='answered'?'Answer from retrieved evidence':'Insufficient evidence'}</h2>${answer.claims.map(claim=>`<div class="draft-note"><p>${esc(claim.text)}</p>${claim.supports.map(s=>`<blockquote>${esc(s.quote)}</blockquote><button class="btn link" data-support="${esc(s.chunk_id)}">View supporting passage →</button>`).join('')}</div>`).join('')}${answer.limitations.map(l=>`<p class="form-hint">${esc(l)}</p>`).join('')}<p class="form-hint">Citation and excerpt checks passed. Scientific support still requires source verification.</p></div></section>` : '';
  el.innerHTML=answerHTML + `<div class="results-meta"><span>${result.hits.length} passages for “${esc(result.question)}”</span><span>${esc(pretty(result.method || 'keyword'))} retrieval · Original excerpts</span></div>` + result.hits.map((hit,i) => {
    const c=hit.chunk; const source=state.sources.find(s=>s.source_id===c.source_id);
    const link=source?.available_locally ? `/api/documents/${encodeURIComponent(c.source_id)}#page=${c.page}` : safeURL(c.file_url || c.source_url);
    return `<article class="result-card"><div class="result-top"><span class="eyebrow" style="margin:0">PASSAGE ${String(i+1).padStart(2,'0')} · ${esc(c.investigation_ids.map(i=>names[i]||i).join(' / '))}</span>${tag(`Page ${c.page}`)}</div><h2>${esc(c.title)}</h2>${c.section?`<span class="muted" style="font-size:11px">Section hint: ${esc(c.section)}</span>`:''}<div class="excerpt">${esc(c.text)}</div><div class="result-footer"><span>${esc(source?.category || 'Document')} · ${esc(c.extraction_method==='pdf_native_text'?'Native PDF text':'Plain text')}</span><a class="btn small" href="${link}" target="_blank" rel="noopener noreferrer">Open cited page ↗</a></div><details><summary>Source details and extraction notes</summary><p><a href="${safeURL(c.source_url)}" target="_blank" rel="noopener noreferrer">Source record ↗</a></p>Chunk: ${esc(c.chunk_id)}<br>SHA-256: ${esc(c.sha256)}${c.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details></article>`;
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
  });
}
async function start() {
  try {
    const [overview, experiments, sources] = await Promise.all([api('/api/overview'),api('/api/experiments'),api('/api/sources')]);
    state.ragStatus=await api('/api/rag-status');
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
start();
