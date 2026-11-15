// Evidence landscape: rotatable 3-D view (canvas, no libraries).
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { LegendShape, Tooltip } from '../../components/common';
import { useApp } from '../../state/AppState';
import { prefersReducedMotion } from '../../lib/format';
import { clampPitch, clampZoom, easeInOut, landHome, pickNearest, project } from '../../lib/landscape';
import type { Camera, Projected } from '../../lib/landscape';
import type { LandPoint, Vec3 } from '../../lib/types';
import { DimSwitch, KindLegend, PointTip } from './LandMap2D';
import type { MapViewProps } from './LandMap2D';

type Drawn = Projected & { p: LandPoint; r: number };
interface Fly { from: { target: Vec3; zoom: number }; to: { target: Vec3; zoom: number }; t0: number; ms: number }

export function Land3D(props: MapViewProps) {
  const { data: d, slots, selected, legendTopics, active, dimRef, onToggleDim } = props;
  const { land, setLand, land3d } = useApp();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tip, setTip] = useState<{ left: number; top: number; content: ReactNode } | null>(null);
  const [spin, setSpinState] = useState<boolean>(() => {
    if (land3d.spin === undefined) land3d.spin = !prefersReducedMotion();
    return land3d.spin;
  });
  const live = useRef(props);
  live.current = props;
  const dirty = useRef(true);
  const stale = useRef(true); // re-read palette colours on the next draw
  const fly = useRef<Fly | null>(null);
  const home = (): Camera => landHome(live.current.data.points);
  const cam = (): Camera => (land3d.cam ||= home());
  const setSpin = (on: boolean) => { land3d.spin = on; setSpinState(on); };
  const setSpinRef = useRef(setSpin);
  setSpinRef.current = setSpin;

  useEffect(() => { dirty.current = true; stale.current = true; }, [d, slots, selected]);

  // Fly to a newly highlighted topic.
  useEffect(() => {
    if (land.flyTo === null) return;
    const c = d.byCluster[land.flyTo];
    const from = cam();
    if (c) fly.current = { from: { target: [...from.target] as Vec3, zoom: from.zoom }, to: { target: c.p3, zoom: Math.max(from.zoom, 2.2) }, t0: performance.now(), ms: prefersReducedMotion() ? 0 : 700 };
    setLand({ flyTo: null });
    setSpin(false);
  }, [land.flyTo]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    let W = 0, H = 0, raf = 0;
    let projected: Drawn[] = [];
    let colors = { s: ['', '', ''], neutral: '', ink: '', ink2: '', surface: '', font: '' };
    const readColors = () => {
      const css = getComputedStyle(document.body), cv = (n: string) => css.getPropertyValue(n).trim();
      colors = { s: [cv('--s1'), cv('--s2'), cv('--s3')], neutral: cv('--neutral'), ink: cv('--ink'), ink2: cv('--ink-2'), surface: cv('--surface'), font: cv('--font') || 'system-ui' };
    };
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      W = canvas.clientWidth; H = Math.min(680, Math.max(420, Math.round(W * 0.68)));
      canvas.style.height = `${H}px`; canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); dirty.current = true;
    };
    const shape = (kind: string, x: number, y: number, r: number) => {
      ctx.beginPath();
      if (kind === 'figure') ctx.rect(x - r, y - r, 2 * r, 2 * r);
      else if (kind === 'table') { const h = r * 1.2; ctx.moveTo(x, y - h); ctx.lineTo(x + h, y + h * 0.8); ctx.lineTo(x - h, y + h * 0.8); ctx.closePath(); }
      else ctx.arc(x, y, r, 0, Math.PI * 2);
    };
    const draw = () => {
      if (stale.current) { readColors(); stale.current = false; }
      const { data, slots: sl, selected: selId } = live.current;
      const c = cam();
      const slotOf = (id: number) => sl.indexOf(id);
      const isActive = sl.some(s => s !== null);
      ctx.clearRect(0, 0, W, H); ctx.fillStyle = colors.surface; ctx.fillRect(0, 0, W, H);
      const next: Drawn[] = [];
      for (const p of data.points) { const q = project(p.p3, c, W, H); if (q) next.push({ p, ...q, r: 0 }); }
      next.sort((a, b) => a.z - b.z); // far to near (painter's order)
      const sel = selId ? data.byId[selId] : null;
      if (sel) {
        const a = project(sel.p3, c, W, H);
        if (a) {
          ctx.save(); ctx.strokeStyle = colors.ink2; ctx.lineWidth = 1.5; ctx.setLineDash([3, 3]);
          for (const id of sel.neighbors) { const n = data.byId[id], b = n && project(n.p3, c, W, H); if (b) { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); } }
          ctx.restore();
        }
      }
      for (const q of next) {
        const slot = q.p.cluster >= 0 ? slotOf(q.p.cluster) : -1;
        const r = Math.max(1.6, Math.min(7, (slot >= 0 ? 4.4 : 3.2) * Math.sqrt(q.s * 2.8)));
        ctx.globalAlpha = slot >= 0 ? 1 : isActive ? 0.32 : Math.max(0.45, Math.min(1, q.s * 2.4));
        ctx.fillStyle = slot >= 0 ? colors.s[slot] : colors.neutral;
        shape(q.p.kind, q.x, q.y, r); ctx.fill();
        ctx.globalAlpha = 1;
        if (slot >= 0 || q.p.id === selId) { ctx.lineWidth = q.p.id === selId ? 2.5 : 1; ctx.strokeStyle = q.p.id === selId ? colors.ink : colors.surface; ctx.stroke(); }
        q.r = r;
      }
      projected = next;
      const labelled = isActive ? data.clusters.filter(cl => slotOf(cl.id) >= 0) : [...data.clusters].sort((a, b) => b.size - a.size).slice(0, 8);
      ctx.font = `${isActive ? 700 : 600} ${isActive ? 13 : 12}px ${colors.font}`; ctx.textAlign = 'center'; ctx.lineJoin = 'round';
      for (const cl of labelled) {
        const q = project(cl.p3, c, W, H); if (!q) continue;
        ctx.lineWidth = 4; ctx.strokeStyle = colors.surface; ctx.strokeText(cl.label, q.x, q.y - 10);
        ctx.fillStyle = isActive ? colors.ink : colors.ink2; ctx.fillText(cl.label, q.x, q.y - 10);
      }
    };
    const loop = (now: number) => {
      const f = fly.current;
      if (f) {
        const c = cam();
        const t = f.ms ? Math.min(1, (now - f.t0) / f.ms) : 1, e = easeInOut(t);
        c.target = f.from.target.map((v, i) => v + (f.to.target[i] - v) * e) as Vec3;
        c.zoom = f.from.zoom + (f.to.zoom - f.from.zoom) * e; dirty.current = true;
        if (t >= 1) fly.current = null;
      }
      if (land3d.spin) { cam().yaw += 0.0025; dirty.current = true; }
      if (dirty.current) { draw(); dirty.current = false; }
      raf = requestAnimationFrame(loop);
    };

    // Interaction: drag to rotate, wheel/pinch to zoom, click to select.
    const pointers = new Map<number, { x: number; y: number }>();
    let moved = 0, pinch0 = 0, zoom0 = 1;
    const stopSpin = () => { if (land3d.spin) setSpinRef.current(false); };
    const onDown = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId); pointers.set(e.pointerId, { x: e.clientX, y: e.clientY }); moved = 0; setTip(null);
      if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch0 = Math.hypot(a.x - b.x, a.y - b.y); zoom0 = cam().zoom; }
    };
    const onMove = (e: PointerEvent) => {
      const prev = pointers.get(e.pointerId);
      if (!prev) { // hover
        const box = canvas.getBoundingClientRect(), q = pickNearest(projected, e.clientX - box.left, e.clientY - box.top);
        if (!q) { setTip(null); canvas.style.cursor = 'grab'; return; }
        canvas.style.cursor = 'pointer';
        setTip({ left: Math.max(0, Math.min(q.x + 14, box.width - 300)), top: Math.min(q.y + 14, box.height - 120), content: <PointTip p={q.p} topicName={live.current.topicName} /> });
        return;
      }
      const dx = e.clientX - prev.x, dy = e.clientY - prev.y; moved += Math.abs(dx) + Math.abs(dy);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const c = cam();
      if (pointers.size === 2) { const [a, b] = [...pointers.values()]; const dist = Math.hypot(a.x - b.x, a.y - b.y); if (pinch0) c.zoom = clampZoom(zoom0 * dist / pinch0); }
      else { c.yaw += dx * 0.008; c.pitch = clampPitch(c.pitch + dy * 0.008); }
      if (moved > 3) { stopSpin(); canvas.style.cursor = 'grabbing'; }
      dirty.current = true;
    };
    const release = (e: PointerEvent) => {
      const wasClick = pointers.size === 1 && moved <= 3; pointers.delete(e.pointerId); if (pointers.size < 2) pinch0 = 0; canvas.style.cursor = 'grab';
      if (wasClick && e.type === 'pointerup') {
        const box = canvas.getBoundingClientRect(), q = pickNearest(projected, e.clientX - box.left, e.clientY - box.top);
        if (q) { stopSpin(); live.current.onSelect(q.p.id); }
      }
    };
    const onLeave = () => { if (!pointers.size) setTip(null); };
    const onWheel = (e: WheelEvent) => { e.preventDefault(); stopSpin(); const c = cam(); c.zoom = clampZoom(c.zoom * Math.exp(-e.deltaY * 0.0015)); dirty.current = true; };
    const onDbl = () => { land3d.cam = home(); dirty.current = true; };
    const onKey = (e: KeyboardEvent) => {
      const k = e.key, step = 0.12, c = cam();
      if (k === 'ArrowLeft') c.yaw -= step; else if (k === 'ArrowRight') c.yaw += step;
      else if (k === 'ArrowUp') c.pitch = Math.max(-1.5, c.pitch - step); else if (k === 'ArrowDown') c.pitch = Math.min(1.5, c.pitch + step);
      else if (k === '+' || k === '=') c.zoom = Math.min(10, c.zoom * 1.2); else if (k === '-' || k === '_') c.zoom = Math.max(0.5, c.zoom / 1.2);
      else if (k === '0') land3d.cam = home(); else return;
      e.preventDefault(); stopSpin(); dirty.current = true;
    };
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerup', release);
    canvas.addEventListener('pointercancel', release);
    canvas.addEventListener('pointerleave', onLeave);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('dblclick', onDbl);
    canvas.addEventListener('keydown', onKey);
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener('pointerdown', onDown);
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', release);
      canvas.removeEventListener('pointercancel', release);
      canvas.removeEventListener('pointerleave', onLeave);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('dblclick', onDbl);
      canvas.removeEventListener('keydown', onKey);
    };
    // The canvas is set up once; it reads the latest props through refs.
  }, []);

  return (
    <>
      <div className="chart-wrap land3d-wrap">
        <DimSwitch three dimRef={dimRef} onToggle={onToggleDim} />
        <canvas ref={canvasRef} className="land3d" tabIndex={0} role="img"
          aria-label={`Rotatable 3-D map of ${d.points.length} indexed items in ${d.clusters.length} topics. Use the topic list view for the same information as a table.`} />
        <Tooltip tip={tip} id="land-tip" />
        <div className="land3d-tools">
          <button type="button" className="btn small" id="land-spin" onClick={() => setSpin(!land3d.spin)}>{spin ? 'Pause spin' : 'Spin'}</button>
          <button type="button" className="btn small" id="land-reset" onClick={() => { land3d.cam = home(); dirty.current = true; }}>Reset view</button>
        </div>
      </div>
      <div className="legend" aria-label="Legend">
        {legendTopics}
        <span><LegendShape shape="circle" color="var(--neutral)" />{active ? 'Other topics' : 'All items'}</span>
        <KindLegend />
      </div>
      <p className="hint">Drag to spin · scroll or pinch to zoom · click a point for details · click a topic above to fly to it · double-click to reset. Arrow keys and +/− work too.</p>
    </>
  );
}
