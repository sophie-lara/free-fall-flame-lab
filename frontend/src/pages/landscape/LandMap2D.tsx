// 2-D evidence map (SVG). One delegated listener set for all ~1,500 points.
import { useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent, ReactNode, RefObject } from 'react';
import { LegendShape, Shape, Tooltip } from '../../components/common';
import { KIND_LABEL, KIND_SHAPE } from '../../lib/landscape';
import type { Slots } from '../../lib/landscape';
import type { LandPoint, LandscapeData } from '../../lib/types';
import { invName } from '../../lib/format';

export interface MapViewProps {
  data: LandscapeData; slots: Slots; selected: string | null; onSelect: (id: string) => void;
  legendTopics: ReactNode[]; active: boolean; dimRef: RefObject<HTMLButtonElement | null>; onToggleDim: () => void;
  topicName: (id: number) => string;
}

export function DimSwitch({ three, dimRef, onToggle }: { three: boolean; dimRef: RefObject<HTMLButtonElement | null>; onToggle: () => void }) {
  return (
    <div className="map-dim ui-switch">
      <span className={`ui-switch-label${three ? '' : ' active'}`}>2D</span>
      <button type="button" ref={dimRef} className="ui-switch-track" role="switch" aria-checked={three} aria-label="3-D view" onClick={onToggle}><span className="ui-switch-knob" /></button>
      <span className={`ui-switch-label${three ? ' active' : ''}`}>3D</span>
    </div>
  );
}

export function KindLegend() {
  return <>{(Object.keys(KIND_SHAPE) as (keyof typeof KIND_SHAPE)[]).map(k => <span key={k}><LegendShape shape={KIND_SHAPE[k]} color="var(--ink-2)" />{KIND_LABEL[k]}</span>)}</>;
}

/** Tooltip text for a point (shared by the 2-D and 3-D views). */
export function PointTip({ p, topicName }: { p: LandPoint; topicName: (id: number) => string }) {
  return <>
    <strong>{p.label || KIND_LABEL[p.kind]}</strong> · {p.filename}{p.page ? `, p. ${p.page}` : ''}<br />
    <span className="muted">{p.investigation ? invName(p.investigation) : ''}{p.cluster >= 0 ? ` · ${topicName(p.cluster)}` : ''}</span><br />
    {p.snippet.slice(0, 160)}{p.snippet.length > 160 ? '…' : ''}
  </>;
}

const W = 880, H = 620, pad = 18;
const sx = (v: number) => pad + v * (W - 2 * pad), sy = (v: number) => pad + (1 - v) * (H - 2 * pad);

export function LandMap2D({ data: d, slots, selected, onSelect, legendTopics, active, dimRef, onToggleDim, topicName }: MapViewProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<{ left: number; top: number; content: ReactNode } | null>(null);
  const sel = selected ? d.byId[selected] : null;

  // Memoized so that moving the tooltip does not re-render every point.
  const marks = useMemo(() => {
    const slotOfC = (id: number) => slots.indexOf(id);
    const order = [...d.points].sort((a, b) => Number(slotOfC(a.cluster) >= 0) - Number(slotOfC(b.cluster) >= 0)); // highlighted on top
    return order.map(p => {
      const slot = p.cluster >= 0 ? slotOfC(p.cluster) : -1;
      const fill = slot >= 0 ? `var(--s${slot + 1})` : 'var(--neutral)';
      const cls = `pt land${slot < 0 && active ? ' dim' : ''}${p.id === selected ? ' selected' : ''}`;
      return <g key={p.id} className="hit" tabIndex={-1} data-pid={p.id}><Shape shape={KIND_SHAPE[p.kind] || 'circle'} x={sx(p.x)} y={sy(p.y)} r={slot >= 0 ? 4.5 : 3.5} className={cls} fill={fill} /></g>;
    });
  }, [d, slots, selected, active]);
  const links = useMemo(() => (sel ? sel.neighbors.map(id => d.byId[id]).filter(Boolean).map(n => (
    <line key={n.id} className="knn" x1={sx(sel.x).toFixed(1)} y1={sy(sel.y).toFixed(1)} x2={sx(n.x).toFixed(1)} y2={sy(n.y).toFixed(1)} />
  )) : null), [d, sel]);
  // Direct labels: highlighted topics, else the largest topics.
  const labels = useMemo(() => {
    const labelled = active ? d.clusters.filter(c => slots.includes(c.id)) : [...d.clusters].sort((a, b) => b.size - a.size).slice(0, 8);
    return labelled.map(c => {
      const x = sx(c.x), y = sy(c.y);
      const anchor = x > W * 0.8 ? 'end' : x < W * 0.2 ? 'start' : 'middle';
      return <text key={c.id} className={`land-label${active ? ' strong' : ''}`} x={x.toFixed(1)} y={y.toFixed(1)} textAnchor={anchor}>{c.label}</text>;
    });
  }, [d, slots, active]);

  const itemAt = (ev: ReactMouseEvent) => (ev.target instanceof Element ? ev.target.closest<SVGGElement>('[data-pid]') : null);
  const onMove = (ev: ReactMouseEvent<SVGSVGElement>) => {
    const g = itemAt(ev); if (!g) { setTip(null); return; }
    const p = d.byId[g.dataset.pid || '']; if (!p) return;
    const box = ev.currentTarget.getBoundingClientRect();
    const px = ev.clientX - box.left, py = ev.clientY - box.top;
    setTip({ left: Math.max(0, Math.min(px + 14, box.width - 300)), top: Math.min(py + 14, box.height - 120), content: <PointTip p={p} topicName={topicName} /> });
  };

  return (
    <>
      <div className="chart-wrap">
        <DimSwitch three={false} dimRef={dimRef} onToggle={onToggleDim} />
        <svg ref={svgRef} className="chart land-map" viewBox={`0 0 ${W} ${H}`} role="img"
          aria-label={`Map of ${d.points.length} indexed items in ${d.clusters.length} topics. The topic list view gives the same information as a table.`}
          onMouseMove={onMove} onMouseLeave={() => setTip(null)}
          onClick={ev => { const g = itemAt(ev); if (g?.dataset.pid) onSelect(g.dataset.pid); }}>
          {links}{marks}{labels}
        </svg>
        <Tooltip tip={tip} id="land-tip" />
      </div>
      <div className="legend" aria-label="Legend">
        {legendTopics}
        <span><LegendShape shape="circle" color="var(--neutral)" />{active ? 'Other topics' : 'All items'}</span>
        <KindLegend />
        {sel ? <span><svg width="22" height="14" aria-hidden="true"><line className="knn" x1="1" y1="7" x2="21" y2="7" /></svg>Link to related evidence</span> : null}
      </div>
      <p className="hint">Hover to preview, click an item for its source and related evidence. Position reflects meaning of the text, not test conditions.</p>
    </>
  );
}
