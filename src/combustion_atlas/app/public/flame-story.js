// "Fire in free fall": a guided, interactive explainer for visitors with no
// combustion background. The flame is an illustration, not a simulation: shapes
// and zone boundaries are schematic. The only numbers shown (about 20 cm/s of
// buoyant flow, 13.5 % and 15.4 % O2) are quoted from indexed NASA reports, and
// every statement links to its source page.

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const docLink = (sourceId, page) => `/api/documents/${encodeURIComponent(sourceId)}#page=${encodeURIComponent(page)}`;

// Indexed sources (source_id = first 16 hex characters of the PDF SHA-256).
const DOCS = {
  bass2: { id: '5ffa911fd9b6356f', label: 'BASS-II summary, NASA/TM-20210011385' },
  bassCrew: { id: '11ad76194acf0958', label: 'BASS crew training, 2011 (PSI-26)' },
  same: { id: '3338abaeec4d5cdf', label: 'SAME smoke experiment, NTRS 20170007283' },
  saffire: { id: 'e38ec36f54817aa9', label: 'Saffire overview, NTRS 20170008805' },
};
// Verbatim excerpts (whitespace normalized) from the indexed text of each page.
const CITES = {
  buoyant: { doc: 'bass2', page: 97, quote: 'the buoyant flow velocity at the base of the flame (20 cm/s' },
  convection: { doc: 'bass2', page: 44, quote: 'natural convection due to gravity' },
  noFlow: { doc: 'bass2', page: 27, quote: 'the opposing flow can be very mild or even completely absent in the absence of buoyancy-induced flow' },
  lowFlowOut: { doc: 'bass2', page: 27, quote: 'Under certain conditions, this can lead to flame extinguishment at a low enough flow velocity.' },
  hemisphere: { doc: 'bass2', page: 97, quote: 'The flame shrinks to a hemispherical blue shape just before quenching.' },
  oscillate: { doc: 'bass2', page: 97, quote: 'Prequenching extinction oscillations at 1.1 Hz are observed' },
  smoke: { doc: 'same', page: 10, quote: 'With the absence of gravity smoke does not rise' },
  limits: { doc: 'bass2', page: 84, quote: 'is significantly lower than the observed upward flame spread limit of 15.4 percent O2' },
  minO2: { doc: 'bass2', page: 84, quote: 'The minimum O2 concentration of 13.5 percent O2' },
  goldilocks: { doc: 'bass2', page: 84, quote: 'This “Goldilocks” zone of flow is unfortunately typical of spacecraft ventilation flows near surfaces.' },
  starved: { doc: 'bass2', page: 97, quote: 'The flames near quenching are starved for O2, which is the limiting reactant.' },
  blowoff: { doc: 'bass2', page: 28, quote: 'finite-rate kinetics in the gas phase becomes important leading ultimately to the blowoff extinction' },
  hole: { doc: 'bass2', page: 97, quote: 'blowoff extinction is initiated by the formation of a hole in the flame sheet' },
  hypothesis: { doc: 'bassCrew', page: 7, quote: 'materials in microgravity burn as well if not better than the same material in normal gravity' },
  standard: { doc: 'bassCrew', page: 7, quote: 'it implies serious safety concerns over the utility and margin of safety provided NASA-STD-6001 Test #1' },
  saffire: { doc: 'saffire', page: 5, quote: 'The Saffire experiments investigated intentionally-set, large-scale fires inside a spacecraft.' },
};

// Schematic limiting-oxygen curves (percent O2) against a 0-100 airflow scale.
// Anchors from BASS-II p84: 13.5 % minimum in gentle microgravity flow, 15.4 %
// normal-gravity upward limit. The curve's shape is illustrative only.
const EARTH_LIMIT = 15.4;
const ORBIT_MIN = 13.5;
export function orbitLimit(flow) {
  if (flow < 15) return ORBIT_MIN + 7 * ((15 - flow) / 15) ** 2; // quenching branch: too little flow
  if (flow <= 60) return ORBIT_MIN + 0.3 * ((flow - 37.5) / 22.5) ** 2; // "Goldilocks" floor
  return ORBIT_MIN + 0.3 + 9 * ((flow - 60) / 40) ** 1.7; // blowoff branch: too much flow
}
export function flameState({ gravity, oxygen, flow }) {
  const limit = gravity === 'earth' ? EARTH_LIMIT : orbitLimit(flow);
  const margin = oxygen - limit;
  const zone = flow < 15 ? 'still' : flow <= 60 ? 'gentle' : 'strong';
  return { limit, margin, zone, burning: margin >= 0, weak: margin >= 0 && margin < 1.5 };
}

const BEATS = [
  {
    title: 'On Earth, flames rise',
    preset: { gravity: 'earth', oxygen: 21, flow: 35 },
    body: 'Light a candle and hot gas, lighter than the air around it, rises. That rising column pulls fresh air in at the base of the flame, about 20 cm/s of it, and stretches the flame into the familiar yellow teardrop. The yellow is glowing soot carried up through the hot tip.',
    cites: ['convection', 'buoyant'],
    ask: 'How does gravity change how a flame spreads?',
  },
  {
    title: 'In orbit, nothing rises',
    preset: { gravity: 'orbit', oxygen: 21, flow: 0 },
    body: 'In orbit, hot gas has no “up” to go to. Nothing rises, not even smoke, so the flame sits in a bubble of its own exhaust and oxygen trickles in only by slow diffusion. It turns round, dim and blue. Starved of air, it shrinks, flickers and can go out on its own.',
    cites: ['noFlow', 'smoke', 'hemisphere', 'lowFlowOut'],
    ask: 'What happens to a flame at very low flow in microgravity?',
  },
  {
    title: 'The Goldilocks breeze',
    preset: { gravity: 'orbit', oxygen: 14, flow: 35 },
    body: 'Now add a gentle breeze, the kind a spacecraft’s ventilation fans make. It brings just enough oxygen without cooling the flame. On the ISS, plastic (PMMA) rods kept burning at 13.5 % oxygen, lower than the 15.4 % at which the same plastic stopped burning in the Earth test. Try it: switch to Earth at 14 % and watch the flame go out.',
    cites: ['minO2', 'limits', 'goldilocks'],
    ask: 'What was the minimum oxygen concentration for PMMA rods burning in microgravity?',
  },
  {
    title: 'Too much wind',
    preset: { gravity: 'orbit', oxygen: 18, flow: 82 },
    body: 'Turn the wind up and the flame can’t hold on. Fuel vapor and oxygen rush past faster than they can react, a hole tears open at the front of the flame, and it blows off, like blowing out a birthday candle. Push the airflow a little further to see it go.',
    cites: ['blowoff', 'hole'],
    ask: 'What causes blowoff extinction of a flame?',
  },
  {
    title: 'Why NASA burns things in space',
    preset: { gravity: 'orbit', oxygen: 21, flow: 35 },
    body: 'Every material that flies on a crewed spacecraft is first screened with a flame test on Earth. But if things burn as well or better in microgravity, that test’s safety margin is in question, and astronauts can’t step outside a burning spacecraft. So NASA burned samples on the ISS (BASS), and even lit large fires inside uncrewed cargo ships after they left the station (Saffire). Combustion Atlas lets you search what those experiments found, and see where the evidence is still thin.',
    cites: ['hypothesis', 'standard', 'saffire'],
    ask: 'What did the Saffire experiments show about flame spread on large samples?',
    explore: true,
  },
];

function explain(s, st) {
  if (s.gravity === 'earth') {
    if (!st.burning) return { title: 'Out: too little oxygen for Earth', body: 'Below about 15.4 % oxygen, this plastic rod did not keep burning in the Earth (normal-gravity) upward test.', cites: ['limits'] };
    return { title: 'Burning on Earth', body: 'On Earth, rising hot gas already pulls in about 20 cm/s of air at the flame’s base, so a gentle fan changes little.', cites: ['buoyant'] };
  }
  if (!st.burning) {
    if (st.zone === 'strong') return { title: 'Out: blown off', body: 'Too much flow for this much oxygen: the gas passes too quickly for the flame chemistry to keep up.', cites: ['blowoff', 'hole'] };
    if (st.zone === 'still') return { title: 'Out: starved of oxygen', body: 'With almost no flow, oxygen arrives only by slow diffusion and the flame goes out.', cites: ['lowFlowOut', 'starved'] };
    return { title: 'Out: below the limit', body: 'Even in the best-case gentle flow, the PMMA rods on the ISS needed at least about 13.5 % oxygen.', cites: ['minO2'] };
  }
  if (st.zone === 'still') return { title: st.weak ? 'Barely burning: a small blue dome' : 'Burning in still air', body: `Without flow, combustion products and smoke stay around the flame instead of rising.${st.weak ? ' Near the limit it shrinks and oscillates before going out.' : ''}`, cites: st.weak ? ['hemisphere', 'oscillate', 'smoke'] : ['smoke', 'noFlow'] };
  if (st.zone === 'strong') return { title: st.weak ? 'About to blow off' : 'Burning in a strong flow', body: st.weak ? 'A hole is opening in the front of the flame; a little more flow and it blows off.' : 'The flame streams downstream; more flow or less oxygen will blow it off.', cites: st.weak ? ['hole'] : ['blowoff'] };
  return { title: s.oxygen < EARTH_LIMIT ? 'Burning where Earth’s test says it would not' : 'Burning in the Goldilocks breeze', body: s.oxygen < EARTH_LIMIT ? 'This oxygen level is below the 15.4 % Earth limit, yet gentle microgravity flow keeps the flame alive.' : 'Gentle ventilation-like flow feeds the flame steadily.', cites: s.oxygen < EARTH_LIMIT ? ['limits', 'goldilocks'] : ['goldilocks'] };
}

// ---------- drawing ----------
const defs = p => `<defs>
  <linearGradient id="${p}-earth" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#fff6d0"/><stop offset=".35" stop-color="#ffd45c"/><stop offset=".75" stop-color="#ff8f2e"/><stop offset="1" stop-color="#e5481d" stop-opacity=".9"/></linearGradient>
  <radialGradient id="${p}-blue" cx=".3" cy=".5" r=".75"><stop offset="0" stop-color="#eef6ff"/><stop offset=".3" stop-color="#8fc0ff"/><stop offset=".7" stop-color="#3a74ff" stop-opacity=".85"/><stop offset="1" stop-color="#2450d8" stop-opacity=".25"/></radialGradient>
  <radialGradient id="${p}-soot" cx=".7" cy=".5" r=".6"><stop offset="0" stop-color="#ffcf6a"/><stop offset="1" stop-color="#ff7a2a" stop-opacity="0"/></radialGradient>
  <filter id="${p}-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>`;
const W = 420, H = 260, TIP = 190, ROD_Y = 150;
function flameSVG(s, st) {
  const earth = s.gravity === 'earth';
  const size = st.burning ? Math.min(1.25, 0.45 + st.margin / 9) : 0;
  const rod = `<rect class="fs-rod" x="${TIP}" y="${ROD_Y - 9}" width="${W - TIP + 4}" height="18" rx="9"/>${st.burning ? '' : `<circle class="fs-char" cx="${TIP + 4}" cy="${ROD_Y}" r="8"/>`}`;
  const arrows = [];
  const flowArrows = n => { for (let i = 0; i < n; i++) { const y = 70 + i * (120 / Math.max(1, n - 1)); const len = 20 + s.flow * 0.45; arrows.push(`<g class="fs-arrow" style="--d:${(i * 0.37) % 1.4}s"><line x1="18" y1="${y}" x2="${18 + len}" y2="${y}"/><path d="M${18 + len} ${y - 5} l8 5 -8 5z"/></g>`); } };
  if (!earth && s.flow >= 3) flowArrows(s.flow < 15 ? 2 : s.flow <= 60 ? 4 : 6);
  if (earth && s.flow >= 3) flowArrows(3);
  let flame = '', smoke = '';
  if (st.burning && earth) {
    const h = 70 + size * 55, w = 20 + size * 10, cx = TIP + 2, cy = ROD_Y - 6;
    const drop = `M${cx} ${cy + w * 0.5} C${cx - w * 1.15} ${cy + w * 0.4} ${cx - w * 0.7} ${cy - h * 0.45} ${cx} ${cy - h} C${cx + w * 0.7} ${cy - h * 0.45} ${cx + w * 1.15} ${cy + w * 0.4} ${cx} ${cy + w * 0.5}Z`;
    const core = `M${cx} ${cy + w * 0.35} C${cx - w * 0.6} ${cy + w * 0.3} ${cx - w * 0.35} ${cy - h * 0.25} ${cx} ${cy - h * 0.5} C${cx + w * 0.35} ${cy - h * 0.25} ${cx + w * 0.6} ${cy + w * 0.3} ${cx} ${cy + w * 0.35}Z`;
    flame = `<g class="fs-flame fs-flicker" filter="url(#st-glow)" style="transform-origin:${cx}px ${cy}px"><path fill="url(#st-earth)" d="${drop}"/><path class="fs-core" d="${core}"/><ellipse class="fs-blue-base" cx="${cx}" cy="${cy + w * 0.3}" rx="${w * 0.8}" ry="${w * 0.35}"/></g>`;
    for (let i = 0; i < 5; i++) smoke += `<circle class="fs-smoke fs-rise" style="--d:${i * 0.6}s" cx="${cx + (i % 2 ? 6 : -6)}" cy="${cy - h - 6}" r="${6 + i}"/>`;
    for (let i = 0; i < 3; i++) arrows.push(`<g class="fs-arrow fs-buoy" style="--d:${i * 0.4}s"><line x1="${cx - 48 + i * 48}" y1="${ROD_Y + 70}" x2="${cx - 48 + i * 48}" y2="${ROD_Y + 30}"/><path d="M${cx - 53 + i * 48} ${ROD_Y + 32} l5 -9 5 9z"/></g>`);
  } else if (st.burning) {
    const r = 16 + size * 14;
    const len = st.zone === 'still' ? r * 0.9 : st.zone === 'gentle' ? r + 30 + s.flow * 0.9 : r + 70 + s.flow * 1.1;
    const thick = st.zone === 'strong' ? r * 0.75 : r;
    const sooty = Math.max(0, Math.min(1, (s.oxygen - 17) / 10)) * (st.zone === 'gentle' ? 1 : 0.5);
    const startX = TIP - (st.zone === 'strong' && st.weak ? -10 : r * 0.9);
    const outline = `M${startX} ${ROD_Y} C${startX} ${ROD_Y - thick * 1.25} ${TIP + len * 0.4} ${ROD_Y - thick} ${TIP + len} ${ROD_Y - 4} L${TIP + len} ${ROD_Y + 4} C${TIP + len * 0.4} ${ROD_Y + thick} ${startX} ${ROD_Y + thick * 1.25} ${startX} ${ROD_Y}Z`;
    flame = `<g class="fs-flame ${st.weak ? 'fs-oscillate' : 'fs-breathe'}" style="transform-origin:${TIP}px ${ROD_Y}px">
      <path fill="url(#st-blue)" filter="url(#st-glow)" d="${outline}"/>
      <path fill="url(#st-soot)" style="opacity:${(sooty * 0.85).toFixed(2)}" transform="translate(${TIP} ${ROD_Y}) scale(0.62 0.55) translate(${-TIP} ${-ROD_Y})" d="${outline}"/>
      ${st.zone === 'strong' && st.weak ? `<rect class="fs-hole" x="${TIP - 14}" y="${ROD_Y - thick}" width="16" height="${thick * 2}"/>` : ''}</g>`;
    const drift = st.zone === 'still' ? 'fs-linger' : 'fs-drift';
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2, rr = r * 1.7;
      smoke += st.zone === 'still'
        ? `<circle class="fs-smoke ${drift}" style="--d:${i * 0.5}s" cx="${TIP + Math.cos(a) * rr}" cy="${ROD_Y + Math.sin(a) * rr}" r="${5 + (i % 3)}"/>`
        : `<circle class="fs-smoke ${drift}" style="--d:${i * 0.45}s" cx="${TIP + len + 8}" cy="${ROD_Y + (i % 3 - 1) * 10}" r="${5 + (i % 3)}"/>`;
    }
  } else {
    for (let i = 0; i < 3; i++) smoke += `<circle class="fs-smoke ${earth ? 'fs-rise' : 'fs-linger'}" style="--d:${i * 0.7}s" cx="${TIP + 4 + i * 6}" cy="${ROD_Y - 14}" r="${4 + i}"/>`;
  }
  const caption = earth ? 'Earth · 1 g' : 'Orbit · microgravity';
  return `<svg class="fs-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Illustration: ${caption}, ${s.oxygen}% oxygen, ${st.zone} airflow. Flame ${st.burning ? (st.weak ? 'barely burning' : 'burning') : 'out'}.`)}">
    ${defs('st')}<rect class="fs-bg ${earth ? 'earth' : 'orbit'}" x="0" y="0" width="${W}" height="${H}" rx="14"/>
    ${earth ? `<text class="fs-g" x="${W - 16}" y="28" text-anchor="end">↓ gravity</text>` : ''}
    <text class="fs-tag" x="16" y="28">${caption}</text>
    ${arrows.join('')}${smoke}${rod}${flame}
    ${st.burning ? '' : `<text class="fs-out" x="${TIP}" y="${ROD_Y + 48}" text-anchor="middle">Flame out</text>`}
    <text class="fs-note" x="16" y="${H - 14}">Illustration</text>
  </svg>`;
}

function mapSVG(s, st) {
  const w = 300, h = 170, m = { l: 34, r: 10, t: 12, b: 34 };
  const sx = f => m.l + (f / 100) * (w - m.l - m.r), sy = o => h - m.b - ((o - 10) / 20) * (h - m.t - m.b);
  let d = '';
  for (let f = 0; f <= 100; f += 2) d += `${f ? 'L' : 'M'}${sx(f).toFixed(1)} ${sy(Math.min(30, orbitLimit(f))).toFixed(1)}`;
  const area = `${d}L${sx(100)} ${sy(30)}L${sx(0)} ${sy(30)}Z`;
  const px = sx(s.flow), py = sy(s.oxygen);
  return `<svg class="fs-map" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(`Schematic flammability map. Current point: ${s.oxygen}% oxygen, ${st.zone} airflow, ${s.gravity === 'earth' ? 'Earth' : 'orbit'}: ${st.burning ? 'burns' : 'out'}.`)}">
    <path class="fs-map-burn" d="${area}"/>
    <path class="fs-map-orbit" d="${d}"/>
    <line class="fs-map-earth" x1="${sx(0)}" x2="${sx(100)}" y1="${sy(EARTH_LIMIT)}" y2="${sy(EARTH_LIMIT)}"/>
    <line class="fs-map-air" x1="${sx(0)}" x2="${sx(100)}" y1="${sy(21)}" y2="${sy(21)}"/>
    <text class="fs-map-lbl" x="${sx(16)}" y="${sy(21) - 4}">air, 21 %</text>
    <text class="fs-map-lbl earth" x="${sx(100) - 2}" y="${sy(EARTH_LIMIT) + 12}" text-anchor="end">Earth 15.4 %</text>
    <text class="fs-map-lbl orbit" x="${sx(37.5)}" y="${sy(ORBIT_MIN) + 13}" text-anchor="middle">orbit 13.5 %</text>
    <line class="fs-axis" x1="${m.l}" x2="${w - m.r}" y1="${h - m.b}" y2="${h - m.b}"/><line class="fs-axis" x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${h - m.b}"/>
    ${[10, 15, 20, 25, 30].map(o => `<text class="fs-tick" x="${m.l - 5}" y="${sy(o) + 3}" text-anchor="end">${o}</text>`).join('')}
    <text class="fs-tick" x="${sx(5)}" y="${h - m.b + 13}" text-anchor="middle">still</text>
    <text class="fs-tick" x="${sx(37.5)}" y="${h - m.b + 13}" text-anchor="middle">gentle</text>
    <text class="fs-tick" x="${sx(82)}" y="${h - m.b + 13}" text-anchor="middle">strong</text>
    <text class="fs-axis-title" x="${(m.l + w - m.r) / 2}" y="${h - 4}" text-anchor="middle">Airflow →</text>
    <text class="fs-axis-title" transform="translate(10 ${(m.t + h - m.b) / 2}) rotate(-90)" text-anchor="middle">Oxygen %</text>
    <circle class="fs-map-pt ${st.burning ? 'on' : 'off'}" cx="${px}" cy="${py}" r="6"/>
  </svg>`;
}

function citesHTML(keys) {
  return keys.map(k => {
    const c = CITES[k], d = DOCS[c.doc];
    return `<li><a href="${docLink(d.id, c.page)}" target="_blank" rel="noopener"><q>${esc(c.quote)}</q> <span class="fs-src">${esc(d.label)}, page ${c.page} ↗</span></a></li>`;
  }).join('');
}

/** Small static 1 g / 0 g flame pair for the hero. */
export function heroFlamesSVG() {
  const drop = (cx, cy, h, w) => `M${cx} ${cy} C${cx - w} ${cy - 2} ${cx - w * 0.6} ${cy - h * 0.5} ${cx} ${cy - h} C${cx + w * 0.6} ${cy - h * 0.5} ${cx + w} ${cy - 2} ${cx} ${cy}Z`;
  return `<svg class="fs-hero-svg" viewBox="0 0 320 240" aria-hidden="true">${defs('hr')}
    <rect class="fs-bg earth" x="4" y="4" width="152" height="232" rx="16"/>
    <rect class="fs-bg orbit" x="164" y="4" width="152" height="232" rx="16"/>
    <g class="fs-flicker" filter="url(#hr-glow)" style="transform-origin:80px 170px"><path fill="url(#hr-earth)" d="${drop(80, 170, 120, 30)}"/><path class="fs-core" d="${drop(80, 168, 58, 15)}"/></g>
    <rect class="fs-wick" x="77" y="168" width="6" height="22" rx="2"/>
    <rect class="fs-wick" x="237" y="150" width="6" height="44" rx="2"/>
    <g class="fs-breathe" style="transform-origin:240px 150px"><circle fill="url(#hr-blue)" filter="url(#hr-glow)" cx="240" cy="150" r="38"/></g>
    <text class="fs-hero-lbl earth" x="80" y="222" text-anchor="middle">Earth · 1 g</text>
    <text class="fs-hero-lbl orbit" x="240" y="222" text-anchor="middle">Orbit · 0 g</text>
  </svg>`;
}

/** Render the story into `root`. `onAsk(question)` opens the Ask page. */
export function renderFlameStory(root, { onAsk } = {}) {
  const s = { beat: 0, ...BEATS[0].preset, free: false };
  root.innerHTML = `
    <div class="section-head fs-head"><div><div class="eyebrow">Start here</div><h2 id="fs-title">Fire in free fall</h2>
      <p class="fs-lead">What happens to a flame without gravity, and why NASA has spent decades finding out. Change gravity, oxygen and airflow to see.</p>
      <p class="fs-disclaimer" role="note">The flame and map are illustrations; quoted passages and page links come from the NASA reports.</p></div></div>
    <div class="card fs-card">
      <ol class="fs-steps" aria-label="Story steps">${BEATS.map((b, i) => `<li><button type="button" class="fs-step" data-beat="${i}"><span>${i + 1}</span>${esc(b.title)}</button></li>`).join('')}</ol>
      <div class="fs-body">
        <div class="fs-left"><div class="fs-stage" id="fs-stage"></div>
          <details class="fs-mapbox" open><summary>Where does this flame sit? (flammability map)</summary><div id="fs-map"></div>
            <p class="hint">Green is where the flame keeps burning in orbit; above the dashed line it burns on Earth. The curve is a sketch; the 13.5 % and 15.4 % marks come from the BASS-II report, page 84.</p></details></div>
        <div class="fs-side">
          <div class="fs-story" aria-live="polite" id="fs-story"></div>
          <fieldset class="fs-controls"><legend>Try it yourself</legend>
            <div class="fs-row"><span class="fs-label" id="fs-g-lbl">Gravity</span>
              <div class="segmented" role="group" aria-labelledby="fs-g-lbl">
                <button type="button" data-g="earth">Earth (1 g)</button><button type="button" data-g="orbit">Orbit (microgravity)</button></div></div>
            <label class="fs-row"><span class="fs-label">Oxygen <output id="fs-o2-out"></output></span>
              <input type="range" id="fs-o2" min="12" max="30" step="0.5" aria-describedby="fs-o2-hint"><span class="hint" id="fs-o2-hint">Air is 21 % oxygen.</span></label>
            <label class="fs-row"><span class="fs-label">Airflow <output id="fs-flow-out"></output></span>
              <input type="range" id="fs-flow" min="0" max="100" step="1" aria-describedby="fs-flow-hint"><span class="hint fs-zones" id="fs-flow-hint"><span>Still</span><span>Gentle, like cabin ventilation</span><span>Strong</span></span></label>
          </fieldset>
        </div>
      </div>
      <div class="fs-nav"><button type="button" class="btn" id="fs-prev">← Back</button><button type="button" class="btn primary" id="fs-next">Next →</button></div>
    </div>`;
  const $ = sel => root.querySelector(sel);
  const o2 = $('#fs-o2'), flow = $('#fs-flow');
  const draw = () => {
    const st = flameState(s);
    $('#fs-stage').innerHTML = flameSVG(s, st);
    $('#fs-map').innerHTML = mapSVG(s, st);
    o2.value = s.oxygen; flow.value = s.flow;
    $('#fs-o2-out').textContent = `${s.oxygen} %`;
    $('#fs-flow-out').textContent = st.zone === 'still' ? 'still' : st.zone === 'gentle' ? 'gentle' : 'strong';
    root.querySelectorAll('[data-g]').forEach(b => { const on = b.dataset.g === s.gravity; b.setAttribute('aria-pressed', String(on)); });
    root.querySelectorAll('[data-beat]').forEach(b => { const on = Number(b.dataset.beat) === s.beat; b.classList.toggle('active', on); b.toggleAttribute('aria-current', on && !s.free); });
    const beat = BEATS[s.beat];
    const live = s.free ? explain(s, st) : beat;
    $('#fs-story').innerHTML = `
      <div class="fs-status ${st.burning ? (st.weak ? 'weak' : 'on') : 'off'}">${st.burning ? (st.weak ? 'Barely burning' : 'Burning') : 'Flame out'}</div>
      <h3>${esc(live.title)}</h3><p>${esc(live.body)}</p>
      <details class="fs-cites"><summary>From the NASA reports (${live.cites.length})</summary><ul>${citesHTML(live.cites)}</ul></details>
      <div class="fs-actions"><button type="button" class="btn small" id="fs-ask">Ask about this →</button>${beat.explore && !s.free ? '<a class="btn small" href="#/explore">See what has been tested →</a>' : ''}${s.free ? '<button type="button" class="btn small link" id="fs-resume">Back to the story</button>' : ''}</div>`;
    $('#fs-ask').addEventListener('click', () => onAsk?.(beat.ask));
    $('#fs-resume')?.addEventListener('click', () => go(s.beat));
    $('#fs-prev').disabled = s.beat === 0 && !s.free;
    $('#fs-next').textContent = s.beat === BEATS.length - 1 ? 'Start over ↺' : 'Next →';
  };
  const go = i => { s.beat = (i + BEATS.length) % BEATS.length; Object.assign(s, BEATS[s.beat].preset, { free: false }); draw(); };
  const tweak = patch => { Object.assign(s, patch, { free: true }); draw(); };
  root.querySelectorAll('[data-beat]').forEach(b => b.addEventListener('click', () => go(Number(b.dataset.beat))));
  root.querySelectorAll('[data-g]').forEach(b => b.addEventListener('click', () => tweak({ gravity: b.dataset.g })));
  o2.addEventListener('input', () => tweak({ oxygen: Number(o2.value) }));
  flow.addEventListener('input', () => tweak({ flow: Number(flow.value) }));
  $('#fs-prev').addEventListener('click', () => go(s.free ? s.beat : s.beat - 1));
  $('#fs-next').addEventListener('click', () => go(s.beat + 1));
  draw();
}
