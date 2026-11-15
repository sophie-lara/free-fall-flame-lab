// "Fire in free fall" explainer. Real NASA photos anchor the story (a candle in normal gravity
// and in microgravity; BASS-II on the ISS); the interactive flame is an illustration in the same
// dark-chamber style that responds to gravity, oxygen and airflow.
import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, RefObject } from 'react';
import {
  BEATS, CITES, DOCS, EARTH_LIMIT, ORBIT_MIN, explain, flameLook, flameState, mixLook, orbitLimit, stageMode, storyDocLink,
} from '../lib/flameStory';
import type { CiteKey, FlameLook, FlameState, Gravity, StageMode, StoryState } from '../lib/flameStory';
import { prefersReducedMotion } from '../lib/format';

const PHOTO_CREDIT = 'Photos: NASA Glenn Research Center (GRC-1998-C-00485).';
const BASS_CREDIT = 'Photo: NASA (ISS040-E-021546).';
const ALT_EARTH = 'Photo: a candle flame in normal gravity, a tall bright yellow teardrop with a blue base, rising from the wick.';
const ALT_ORBIT = 'Photo: a candle flame in microgravity, a small dim blue dome wrapped around the wick.';
const ALT_BASS = 'Photo: NASA astronaut Reid Wiseman conducting a BASS-II combustion experiment in the Microgravity Science Glovebox aboard the International Space Station, June 26, 2014.';

const cssVar = (name: string, value: string | number): CSSProperties => ({ [name as string]: value } as CSSProperties);

// ---------- motion helpers ----------
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const mq = matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/** True while the element is on screen; animations pause when it is not. */
function useOnScreen(ref: RefObject<Element | null>): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver !== 'function') return;
    const io = new IntersectionObserver(entries => setVisible(entries.some(e => e.isIntersecting)), { rootMargin: '80px' });
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return visible;
}

/** Eases the flame's look to a new target over ~420 ms (instant with reduced motion). */
function useTweenedLook(target: FlameLook, reduced: boolean): FlameLook {
  const [look, setLook] = useState(target);
  const current = useRef(target);
  const key = JSON.stringify(target);
  useEffect(() => {
    if (reduced) { current.current = target; setLook(target); return; }
    const from = current.current, t0 = performance.now(), ms = 420;
    let raf = requestAnimationFrame(function step(now) {
      const t = Math.min(1, (now - t0) / ms), e = 1 - (1 - t) ** 3;
      current.current = mixLook(from, target, e);
      setLook(current.current);
      if (t < 1) raf = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(raf);
  }, [key, reduced]);
  return look;
}

// ---------- the illustrated flame ----------
const W = 420, H = 260, TIP = 180, ROD_Y = 150;
const STREAKS = [0.16, 0.3, 0.44, 0.58, 0.72, 0.86].map((f, i) => ({ y: 40 + f * 180, delay: (i * 0.53) % 1.7, len: 30 + (i % 3) * 14 }));

function DrawnFlame({ s, st, look, animate }: { s: StoryState; st: FlameState; look: FlameLook; animate: boolean }) {
  const { earth, alpha, size, glow, soot, len, thick, flow } = look;
  const orbit = 1 - earth;
  // Earth: a rising teardrop with a blue base.
  const h = 70 + size * 55, w = 20 + size * 10, cx = TIP + 2, cy = ROD_Y - 6;
  const drop = `M${cx} ${cy + w * 0.5} C${cx - w * 1.15} ${cy + w * 0.4} ${cx - w * 0.7} ${cy - h * 0.45} ${cx} ${cy - h} C${cx + w * 0.7} ${cy - h * 0.45} ${cx + w * 1.15} ${cy + w * 0.4} ${cx} ${cy + w * 0.5}Z`;
  const core = `M${cx} ${cy + w * 0.3} C${cx - w * 0.55} ${cy + w * 0.2} ${cx - w * 0.32} ${cy - h * 0.3} ${cx} ${cy - h * 0.62} C${cx + w * 0.32} ${cy - h * 0.3} ${cx + w * 0.55} ${cy + w * 0.2} ${cx} ${cy + w * 0.3}Z`;
  // Orbit: an envelope around the rod tip, streaming downstream with the flow.
  const r = 16 + size * 14;
  const lift = st.zone === 'strong' && st.weak ? -10 : r * 0.9;
  const startX = TIP - lift;
  const outline = `M${startX} ${ROD_Y} C${startX} ${ROD_Y - thick * 1.25} ${TIP + len * 0.4} ${ROD_Y - thick} ${TIP + len} ${ROD_Y - 4} L${TIP + len} ${ROD_Y + 4} C${TIP + len * 0.4} ${ROD_Y + thick} ${startX} ${ROD_Y + thick * 1.25} ${startX} ${ROD_Y}Z`;
  const streakOpacity = flow < 3 ? 0 : Math.min(0.45, 0.12 + flow / 260);
  const streakDur = `${Math.max(0.9, 3.4 - flow * 0.026).toFixed(2)}s`;
  const caption = s.gravity === 'earth' ? 'Earth · 1 g' : 'Orbit · microgravity';
  const label = `Illustration: ${caption}, ${s.oxygen}% oxygen, ${st.zone} airflow. Flame ${st.burning ? (st.weak ? 'barely burning' : 'burning') : 'out'}.`;
  const turbulence = animate
    ? <animate attributeName="baseFrequency" dur="2.6s" values="0.008 0.024;0.011 0.034;0.009 0.028;0.008 0.024" repeatCount="indefinite" />
    : null;
  return (
    <svg className="fs-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <defs>
        <radialGradient id="fx-bg" cx=".45" cy=".55" r=".75"><stop offset="0" stopColor="#141d31" /><stop offset=".55" stopColor="#090d17" /><stop offset="1" stopColor="#030409" /></radialGradient>
        <radialGradient id="fx-earth" cx=".5" cy=".64" r=".62"><stop offset="0" stopColor="#fff9ea" /><stop offset=".32" stopColor="#ffe09a" /><stop offset=".62" stopColor="#ff9a3c" stopOpacity=".95" /><stop offset=".86" stopColor="#d9531e" stopOpacity=".55" /><stop offset="1" stopColor="#a33212" stopOpacity="0" /></radialGradient>
        <radialGradient id="fx-earth-blue" cx=".5" cy=".7" r=".6"><stop offset="0" stopColor="#c9dcff" stopOpacity=".7" /><stop offset=".5" stopColor="#5d86ff" stopOpacity=".75" /><stop offset="1" stopColor="#2a4bd8" stopOpacity="0" /></radialGradient>
        <radialGradient id="fx-glow-warm" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#ffb257" stopOpacity=".55" /><stop offset="1" stopColor="#ff7a2a" stopOpacity="0" /></radialGradient>
        <radialGradient id="fx-orbit" cx=".32" cy=".5" r=".72"><stop offset="0" stopColor="#1a1030" stopOpacity=".2" /><stop offset=".45" stopColor="#d58ad8" stopOpacity=".28" /><stop offset=".74" stopColor="#5a7dff" stopOpacity=".78" /><stop offset=".92" stopColor="#3554f0" stopOpacity=".55" /><stop offset="1" stopColor="#2240d8" stopOpacity="0" /></radialGradient>
        <radialGradient id="fx-orbit-soot" cx=".6" cy=".5" r=".6"><stop offset="0" stopColor="#ffcf6a" /><stop offset="1" stopColor="#ff7a2a" stopOpacity="0" /></radialGradient>
        <radialGradient id="fx-glow-cool" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#5b84ff" stopOpacity=".5" /><stop offset="1" stopColor="#3150e0" stopOpacity="0" /></radialGradient>
        <linearGradient id="fx-rod" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#dfe7f2" /><stop offset=".45" stopColor="#a4b3c8" /><stop offset="1" stopColor="#5a6a82" /></linearGradient>
        <linearGradient id="fx-metal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#3a4352" /><stop offset=".45" stopColor="#8a95a6" /><stop offset="1" stopColor="#323a47" /></linearGradient>
        <filter id="fx-blur-lg" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="12" /></filter>
        <filter id="fx-blur-sm" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.6" /></filter>
        <filter id="fx-smoke" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="4" /></filter>
        <filter id="fx-flicker" x="-30%" y="-30%" width="160%" height="160%">
          <feTurbulence type="fractalNoise" baseFrequency="0.008 0.024" numOctaves="1" seed="4" result="n">{turbulence}</feTurbulence>
          <feDisplacementMap in="SourceGraphic" in2="n" scale={3 + 3 * size} xChannelSelector="R" yChannelSelector="G" />
        </filter>
        <filter id="fx-flicker-soft" x="-30%" y="-30%" width="160%" height="160%">
          <feTurbulence type="fractalNoise" baseFrequency="0.02 0.02" numOctaves="2" seed="9" result="n">{animate ? <animate attributeName="baseFrequency" dur="3.4s" values="0.02 0.02;0.026 0.03;0.02 0.02" repeatCount="indefinite" /> : null}</feTurbulence>
          <feDisplacementMap in="SourceGraphic" in2="n" scale="3.5" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
      <rect x="0" y="0" width={W} height={H} rx="14" fill="url(#fx-bg)" />
      <rect className="fs-window" x="10" y="10" width={W - 20} height={H - 20} rx="10" />
      {/* airflow: faint streaks drifting past the sample */}
      <g className="fs-streaks" style={{ opacity: streakOpacity, ...cssVar('--dur', streakDur) }} aria-hidden="true">
        {STREAKS.map((k, i) => <line key={i} className="fs-streak" x1={-k.len} x2="0" y1={k.y} y2={k.y} style={cssVar('--d', `${-k.delay}s`)} />)}
      </g>
      {/* Earth: buoyant air drawn up into the flame's base */}
      <g className="fs-buoyant" style={{ opacity: earth * alpha * 0.5 }} aria-hidden="true">
        {[-44, -24, 26, 46].map((dx, i) => <line key={i} className="fs-rise-streak" x1={cx + dx} x2={cx + dx * 0.7} y1={ROD_Y + 70} y2={ROD_Y + 26} style={cssVar('--d', `${-i * 0.6}s`)} />)}
      </g>
      {/* sample: a PMMA rod in a metal holder */}
      <rect x="346" y={ROD_Y + 14} width="12" height={H - ROD_Y - 14} fill="url(#fx-metal)" opacity=".8" />
      <rect x={TIP} y={ROD_Y - 8} width={W - TIP} height="16" rx="8" fill="url(#fx-rod)" />
      <line x1={TIP + 8} x2={W} y1={ROD_Y - 4} y2={ROD_Y - 4} stroke="#fff" strokeOpacity=".35" strokeWidth="1.5" />
      <rect x="338" y={ROD_Y - 15} width="28" height="30" rx="4" fill="url(#fx-metal)" />
      <circle cx={TIP + 3} cy={ROD_Y} r="7" fill="#2a2320" opacity={Math.max(0, 1 - alpha) * 0.9} />
      {/* glow (additive) */}
      <g className="fs-additive" style={{ opacity: alpha * glow }}>
        <ellipse cx={cx} cy={cy - h * 0.42} rx={w * 2.3} ry={h * 0.78} fill="url(#fx-glow-warm)" filter="url(#fx-blur-lg)" opacity={earth} />
        <ellipse cx={TIP + len * 0.32} cy={ROD_Y} rx={len * 0.62 + r} ry={thick * 1.7} fill="url(#fx-glow-cool)" filter="url(#fx-blur-lg)" opacity={orbit} />
      </g>
      {/* Earth flame */}
      <g className="fs-flame fs-flame-earth" filter="url(#fx-flicker)" style={{ opacity: alpha * earth, transformOrigin: `${cx}px ${cy}px` }}>
        <path d={drop} fill="url(#fx-earth)" filter="url(#fx-blur-sm)" style={{ opacity: 0.55 + 0.45 * glow }} />
        <path d={drop} fill="url(#fx-earth-blue)" filter="url(#fx-blur-sm)" style={{ opacity: (1 - soot) * 0.85 }} />
        <path d={core} fill="#fff6dc" filter="url(#fx-blur-sm)" style={{ opacity: 0.6 * glow * soot }} />
        <ellipse cx={cx} cy={cy + w * 0.28} rx={w * 0.85} ry={w * 0.38} fill="#4b78ff" filter="url(#fx-blur-sm)" opacity=".6" />
        <ellipse cx={cx} cy={cy + 1} rx="3.5" ry="7" fill="#1d140e" opacity=".45" />
      </g>
      {/* Orbit flame */}
      <g className={`fs-flame ${st.weak ? 'fs-oscillate' : 'fs-breathe'}`} filter="url(#fx-flicker-soft)" style={{ opacity: alpha * orbit, transformOrigin: `${TIP}px ${ROD_Y}px` }}>
        <path d={outline} fill="url(#fx-orbit)" filter="url(#fx-blur-sm)" style={{ opacity: 0.5 + 0.5 * glow }} />
        <path d={outline} fill="none" stroke="#6b8cff" strokeWidth="2.2" filter="url(#fx-blur-sm)" style={{ opacity: 0.35 + 0.4 * glow }} />
        <path d={outline} fill="url(#fx-orbit-soot)" transform={`translate(${TIP} ${ROD_Y}) scale(0.62 0.55) translate(${-TIP} ${-ROD_Y})`} style={{ opacity: soot * 0.85 }} />
        {st.zone === 'strong' && st.weak ? <ellipse cx={TIP - 4} cy={ROD_Y} rx="7" ry={thick * 0.9} fill="#0b101c" opacity=".85" filter="url(#fx-smoke)" /> : null}
      </g>
      {/* extinction: a brief smoke wisp */}
      {st.burning ? null : (
        <g key={`${s.gravity}-${s.oxygen}-${s.flow}`} className={`fs-wisp ${s.gravity === 'earth' ? 'up' : 'drift'}`} filter="url(#fx-smoke)" aria-hidden="true">
          <circle cx={TIP + 2} cy={ROD_Y - 12} r="6" /><circle cx={TIP + 8} cy={ROD_Y - 22} r="8" /><circle cx={TIP} cy={ROD_Y - 34} r="10" />
        </g>
      )}
      <text className="fs-tag" x="18" y="30">{caption}</text>
      <text className="fs-g" x={W - 18} y="30" textAnchor="end" style={{ opacity: earth }}>↓ gravity</text>
      {st.burning ? null : <text className="fs-out" x={TIP} y={ROD_Y + 50} textAnchor="middle">Flame out</text>}
      <text className="fs-note" x="18" y={H - 16}>Illustration</text>
    </svg>
  );
}

// ---------- flammability map (same dark stage) ----------
function FlammabilityMap({ s, st }: { s: StoryState; st: FlameState }) {
  const w = 300, h = 170, m = { l: 34, r: 10, t: 12, b: 34 };
  const sx = (f: number) => m.l + (f / 100) * (w - m.l - m.r), sy = (o: number) => h - m.b - ((o - 10) / 20) * (h - m.t - m.b);
  let d = '';
  for (let f = 0; f <= 100; f += 2) d += `${f ? 'L' : 'M'}${sx(f).toFixed(1)} ${sy(Math.min(30, orbitLimit(f))).toFixed(1)}`;
  const area = `${d}L${sx(100)} ${sy(30)}L${sx(0)} ${sy(30)}Z`;
  return (
    <svg className="fs-map" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`Schematic flammability map. Current point: ${s.oxygen}% oxygen, ${st.zone} airflow, ${s.gravity === 'earth' ? 'Earth' : 'orbit'}: ${st.burning ? 'burns' : 'out'}.`}>
      <path className="fs-map-burn" d={area} />
      <path className="fs-map-orbit" d={d} />
      <line className="fs-map-earth" x1={sx(0)} x2={sx(100)} y1={sy(EARTH_LIMIT)} y2={sy(EARTH_LIMIT)} />
      <line className="fs-map-air" x1={sx(0)} x2={sx(100)} y1={sy(21)} y2={sy(21)} />
      <text className="fs-map-lbl" x={sx(16)} y={sy(21) - 4}>air, 21 %</text>
      <text className="fs-map-lbl earth" x={sx(100) - 2} y={sy(EARTH_LIMIT) + 12} textAnchor="end">Earth 15.4 %</text>
      <text className="fs-map-lbl orbit" x={sx(37.5)} y={sy(ORBIT_MIN) + 13} textAnchor="middle">orbit 13.5 %</text>
      <line className="fs-axis" x1={m.l} x2={w - m.r} y1={h - m.b} y2={h - m.b} /><line className="fs-axis" x1={m.l} x2={m.l} y1={m.t} y2={h - m.b} />
      {[10, 15, 20, 25, 30].map(o => <text key={o} className="fs-tick" x={m.l - 5} y={sy(o) + 3} textAnchor="end">{o}</text>)}
      <text className="fs-tick" x={sx(5)} y={h - m.b + 13} textAnchor="middle">still</text>
      <text className="fs-tick" x={sx(37.5)} y={h - m.b + 13} textAnchor="middle">gentle</text>
      <text className="fs-tick" x={sx(82)} y={h - m.b + 13} textAnchor="middle">strong</text>
      <text className="fs-axis-title" x={(m.l + w - m.r) / 2} y={h - 4} textAnchor="middle">Airflow →</text>
      <text className="fs-axis-title" transform={`translate(10 ${(m.t + h - m.b) / 2}) rotate(-90)`} textAnchor="middle">Oxygen %</text>
      <circle className={`fs-map-pt ${st.burning ? 'on' : 'off'}`} cx={sx(s.flow)} cy={sy(s.oxygen)} r="6" />
      <text className="fs-map-note" x={w - m.r} y={m.t + 8} textAnchor="end">Illustration</text>
    </svg>
  );
}

function Cites({ keys }: { keys: CiteKey[] }) {
  return (
    <ul>
      {keys.map(k => {
        const c = CITES[k], d = DOCS[c.doc];
        return <li key={k}><a href={storyDocLink(d.id, c.page)} target="_blank" rel="noopener"><q>{c.quote}</q> <span className="fs-src">{d.label}, page {c.page} ↗</span></a></li>;
      })}
    </ul>
  );
}

/** The real candle-flame photo pair for the hero: Earth (1 g) and orbit (0 g). */
export function HeroFlames() {
  return (
    <span className="fs-hero-pair">
      <span className="fs-hero-card"><img src="/flame-earth-1g.jpg" alt={ALT_EARTH} width="441" height="700" /><span className="fs-cap fs-hero-lbl">Earth · 1 g</span></span>
      <span className="fs-hero-card"><img src="/flame-orbit-0g.jpg" alt={ALT_ORBIT} width="455" height="700" /><span className="fs-cap fs-hero-lbl">Orbit · 0 g</span></span>
    </span>
  );
}
export const HERO_CREDIT = PHOTO_CREDIT;

function Stage({ mode, s, st, look, animate }: { mode: StageMode; s: StoryState; st: FlameState; look: FlameLook; animate: boolean }) {
  const earth = s.gravity === 'earth';
  return (
    <div className="fs-frame fs-stage-frame">
      <div className={`fs-layer fs-photos${mode === 'photos' ? ' on' : ''}`} aria-hidden={mode !== 'photos'}>
        <figure className={`fs-photo${earth ? ' active' : ''}`}>
          <img src="/flame-earth-1g.jpg" alt={mode === 'photos' ? ALT_EARTH : ''} loading="lazy" width="441" height="700" />
          <figcaption className="fs-cap">Earth · 1 g</figcaption>
        </figure>
        <figure className={`fs-photo${earth ? '' : ' active'}`}>
          <img src="/flame-orbit-0g.jpg" alt={mode === 'photos' ? ALT_ORBIT : ''} loading="lazy" width="455" height="700" />
          <figcaption className="fs-cap">Orbit · microgravity</figcaption>
        </figure>
        <span className="fs-credit">{PHOTO_CREDIT}</span>
      </div>
      <div className={`fs-layer fs-bass${mode === 'bass' ? ' on' : ''}`} aria-hidden={mode !== 'bass'}>
        <img src="/bass2-wiseman-iss.jpg" alt={mode === 'bass' ? ALT_BASS : ''} loading="lazy" width="1280" height="851" />
        <span className="fs-cap fs-bass-cap">BASS-II · International Space Station</span>
        <span className="fs-credit">{BASS_CREDIT}</span>
      </div>
      <div className={`fs-layer fs-drawn${mode === 'drawn' ? ' on' : ''}`} aria-hidden={mode !== 'drawn'}>
        <DrawnFlame s={s} st={st} look={look} animate={animate} />
      </div>
    </div>
  );
}

interface Story extends StoryState { beat: number; free: boolean; touched: boolean }

/** The story; `onAsk(question)` opens the Ask page. */
export function FlameStory({ onAsk }: { onAsk?: (q: string) => void }) {
  const [s, setS] = useState<Story>({ beat: 0, ...BEATS[0].preset, free: false, touched: false });
  const st = flameState(s);
  const reduced = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const onScreen = useOnScreen(stageRef);
  const look = useTweenedLook(flameLook(s, st), reduced);
  const mode = stageMode(s.beat, s.free, s.touched);

  // Pause the SVG flicker (SMIL) off screen; CSS animations pause through a class.
  useEffect(() => {
    stageRef.current?.querySelectorAll('svg').forEach(svg => { if (onScreen) svg.unpauseAnimations(); else svg.pauseAnimations(); });
  }, [onScreen, mode]);

  const go = (i: number) => setS(prev => {
    const beat = (i + BEATS.length) % BEATS.length;
    return { ...prev, beat, ...BEATS[beat].preset, free: false, touched: false };
  });
  const tweak = (patch: Partial<StoryState>, touches: boolean) => setS(prev => ({ ...prev, ...patch, free: true, touched: prev.touched || touches }));
  const beat = BEATS[s.beat];
  const live = s.free ? explain(s, st) : beat;
  const status = st.burning ? (st.weak ? 'weak' : 'on') : 'off';
  return (
    <>
      <div className="section-head fs-head"><div><div className="eyebrow">Start here</div><h2 id="fs-title">Fire in free fall</h2>
        <p className="fs-lead">What happens to a flame without gravity, and why NASA has spent decades finding out. Change gravity, oxygen and airflow to see.</p>
        <p className="fs-disclaimer" role="note">The flame and map are illustrations; quoted passages and page links come from the NASA reports.</p></div></div>
      <div className={`card fs-card${onScreen ? '' : ' fs-paused'}`}>
        <ol className="fs-steps" aria-label="Story steps">
          {BEATS.map((b, i) => {
            const on = i === s.beat;
            return <li key={b.title}><button type="button" className={`fs-step${on ? ' active' : ''}`} aria-current={on && !s.free ? 'step' : undefined} onClick={() => go(i)}><span>{i + 1}</span>{b.title}</button></li>;
          })}
        </ol>
        <div className="fs-body">
          <div className="fs-left">
            <div className="fs-stage" id="fs-stage" ref={stageRef}><Stage mode={mode} s={s} st={st} look={look} animate={!reduced} /></div>
            <details className="fs-mapbox" open><summary>Where does this flame sit? (flammability map)</summary>
              <div id="fs-map" className="fs-frame fs-map-frame"><FlammabilityMap s={s} st={st} /></div>
              <p className="hint">Green is where the flame keeps burning in orbit; above the dashed line it burns on Earth. The curve is a sketch; the 13.5 % and 15.4 % marks come from the BASS-II report, page 84.</p></details>
          </div>
          <div className="fs-side">
            <div className="fs-story" aria-live="polite" id="fs-story">
              <div className="fs-story-anim" key={`${s.beat}-${s.free ? live.title : 'beat'}`}>
                <div className={`fs-status ${status}`}>{st.burning ? (st.weak ? 'Barely burning' : 'Burning') : 'Flame out'}</div>
                <h3>{live.title}</h3><p>{live.body}</p>
              </div>
              <details className="fs-cites"><summary>From the NASA reports ({live.cites.length})</summary><Cites keys={live.cites} /></details>
              <div className="fs-actions">
                <button type="button" className="btn small" id="fs-ask" onClick={() => onAsk?.(beat.ask)}>Ask about this →</button>
                {beat.explore && !s.free ? <a className="btn small" href="#/explore">See what has been tested →</a> : null}
                {s.free ? <button type="button" className="btn small link" id="fs-resume" onClick={() => go(s.beat)}>Back to the story</button> : null}
              </div>
            </div>
            <fieldset className="fs-controls"><legend>Try it yourself</legend>
              <div className="fs-row"><span className="fs-label" id="fs-g-lbl">Gravity</span>
                <div className="segmented" role="group" aria-labelledby="fs-g-lbl">
                  {(['earth', 'orbit'] as Gravity[]).map(g => (
                    <button key={g} type="button" aria-pressed={g === s.gravity} onClick={() => tweak({ gravity: g }, false)}>{g === 'earth' ? 'Earth (1 g)' : 'Orbit (microgravity)'}</button>
                  ))}
                </div></div>
              <label className="fs-row"><span className="fs-label">Oxygen <output id="fs-o2-out">{`${s.oxygen} %`}</output></span>
                <input type="range" id="fs-o2" min="12" max="30" step="0.5" aria-describedby="fs-o2-hint" value={s.oxygen} onChange={e => tweak({ oxygen: Number(e.target.value) }, true)} />
                <span className="hint" id="fs-o2-hint">Air is 21 % oxygen.</span></label>
              <label className="fs-row"><span className="fs-label">Airflow <output id="fs-flow-out">{st.zone}</output></span>
                <input type="range" id="fs-flow" min="0" max="100" step="1" aria-describedby="fs-flow-hint" value={s.flow} onChange={e => tweak({ flow: Number(e.target.value) }, true)} />
                <span className="hint fs-zones" id="fs-flow-hint"><span>Still</span><span>Gentle, like cabin ventilation</span><span>Strong</span></span></label>
            </fieldset>
          </div>
        </div>
        <div className="fs-nav">
          <button type="button" className="btn" id="fs-prev" disabled={s.beat === 0 && !s.free} onClick={() => go(s.free ? s.beat : s.beat - 1)}>← Back</button>
          <button type="button" className="btn primary" id="fs-next" onClick={() => go(s.beat + 1)}>{s.beat === BEATS.length - 1 ? 'Start over ↺' : 'Next →'}</button>
        </div>
      </div>
    </>
  );
}
