// "Fire in free fall": a guided, interactive explainer for visitors with no
// combustion background. The flame is an illustration, not a simulation: shapes
// and zone boundaries are schematic. The only numbers shown (about 20 cm/s of
// buoyant flow, 13.5 % and 15.4 % O2) are quoted from indexed NASA reports, and
// every statement links to its source page.

export type Gravity = 'earth' | 'orbit';
export interface StoryState { gravity: Gravity; oxygen: number; flow: number }
export type Zone = 'still' | 'gentle' | 'strong';
export interface FlameState { limit: number; margin: number; zone: Zone; burning: boolean; weak: boolean }

// Indexed sources (source_id = first 16 hex characters of the PDF SHA-256).
export const DOCS = {
  bass2: { id: '5ffa911fd9b6356f', label: 'BASS-II summary, NASA/TM-20210011385' },
  bassCrew: { id: '11ad76194acf0958', label: 'BASS crew training, 2011 (PSI-26)' },
  same: { id: '3338abaeec4d5cdf', label: 'SAME smoke experiment, NTRS 20170007283' },
  saffire: { id: 'e38ec36f54817aa9', label: 'Saffire overview, NTRS 20170008805' },
} as const;
type DocKey = keyof typeof DOCS;

// Verbatim excerpts (whitespace normalized) from the indexed text of each page.
export const CITES = {
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
} satisfies Record<string, { doc: DocKey; page: number; quote: string }>;
export type CiteKey = keyof typeof CITES;

export const storyDocLink = (sourceId: string, page: number): string =>
  `/api/documents/${encodeURIComponent(sourceId)}#page=${encodeURIComponent(page)}`;

// Schematic limiting-oxygen curves (percent O2) against a 0-100 airflow scale.
// Anchors from BASS-II p84: 13.5 % minimum in gentle microgravity flow, 15.4 %
// normal-gravity upward limit. The curve's shape is illustrative only.
export const EARTH_LIMIT = 15.4;
export const ORBIT_MIN = 13.5;
export function orbitLimit(flow: number): number {
  if (flow < 15) return ORBIT_MIN + 7 * ((15 - flow) / 15) ** 2; // quenching branch: too little flow
  if (flow <= 60) return ORBIT_MIN + 0.3 * ((flow - 37.5) / 22.5) ** 2; // "Goldilocks" floor
  return ORBIT_MIN + 0.3 + 9 * ((flow - 60) / 40) ** 1.7; // blowoff branch: too much flow
}
export function flameState({ gravity, oxygen, flow }: StoryState): FlameState {
  const limit = gravity === 'earth' ? EARTH_LIMIT : orbitLimit(flow);
  const margin = oxygen - limit;
  const zone: Zone = flow < 15 ? 'still' : flow <= 60 ? 'gentle' : 'strong';
  return { limit, margin, zone, burning: margin >= 0, weak: margin >= 0 && margin < 1.5 };
}

export interface Beat { title: string; preset: StoryState; body: string; cites: CiteKey[]; ask: string; explore?: boolean }

export const BEATS: Beat[] = [
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
    body: 'Materials for the cabins of US spacecraft are screened with an upward flame test on Earth (NASA-STD-6001 Test 1). But if things burn as well or better in microgravity, that test’s safety margin is in question, and astronauts can’t step outside a burning spacecraft. So NASA burned samples on the ISS (BASS), and even lit large fires inside uncrewed cargo ships after they left the station (Saffire). Combustion Atlas lets you search what those experiments found, and see where the evidence is still thin.',
    cites: ['hypothesis', 'standard', 'saffire'],
    ask: 'What did the Saffire experiments show about flame spread on large samples?',
    explore: true,
  },
];

export function explain(s: StoryState, st: FlameState): { title: string; body: string; cites: CiteKey[] } {
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

// ---------- how the illustrated flame looks (numbers are tweened between states) ----------
export interface FlameLook {
  /** 1 on Earth, 0 in orbit: crossfades the rising teardrop and the orbit envelope. */
  earth: number;
  /** 1 while burning, 0 when out: the flame fades out on extinction. */
  alpha: number;
  /** Overall flame scale. */
  size: number;
  /** Glow and core brightness, lower near the oxygen limit. */
  glow: number;
  /** Yellow-orange sooty core, against a bluer flame at low oxygen. */
  soot: number;
  /** Orbit: downstream length and half-thickness of the envelope (px in the 420x260 stage). */
  len: number;
  thick: number;
  /** Airflow, 0-100, for the drifting streaks. */
  flow: number;
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export function flameLook(s: StoryState, st: FlameState): FlameLook {
  const earth = s.gravity === 'earth' ? 1 : 0;
  const size = st.burning ? clamp(0.45 + st.margin / 9, 0.3, 1.25) : 0.35;
  const glow = st.burning ? clamp(0.45 + st.margin / 7, 0.4, 1) : 0;
  const soot = earth
    ? clamp((s.oxygen - 14) / 8, 0.15, 1)
    : clamp((s.oxygen - 17) / 10, 0, 1) * (st.zone === 'gentle' ? 1 : 0.5);
  const r = 16 + size * 14;
  const len = st.zone === 'still' ? r * 0.9 : st.zone === 'gentle' ? r + 30 + s.flow * 0.9 : r + 70 + s.flow * 1.1;
  const thick = st.zone === 'strong' ? r * 0.75 : r;
  return { earth, alpha: st.burning ? 1 : 0, size, glow, soot, len, thick, flow: s.flow };
}

export const mixLook = (a: FlameLook, b: FlameLook, t: number): FlameLook => {
  const out = { ...a };
  (Object.keys(a) as (keyof FlameLook)[]).forEach(k => { out[k] = a[k] + (b[k] - a[k]) * t; });
  return out;
};

/** Which picture the stage shows: the real photo pair, the BASS-II photo, or the illustration. */
export type StageMode = 'photos' | 'bass' | 'drawn';
export function stageMode(beat: number, free: boolean, touched: boolean): StageMode {
  if (beat <= 1 && !touched) return 'photos'; // gravity alone switches the photo pair
  if (beat === 4 && !free) return 'bass';
  return 'drawn';
}
