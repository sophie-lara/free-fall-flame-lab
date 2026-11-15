// Coverage heatmap (bins and cell classes come from the server).
import { useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import { Tooltip } from '../../components/common';
import {
  CELL_CLASSES, CLASS_LABEL, axisTitle, binText, cellAt, cellSummary, gridView, heatmapLayout, xLabelLines,
} from '../../lib/coverage';
import { count } from '../../lib/format';
import type { Cell, CellClass, Coverage, Grid, GridGap } from '../../lib/types';
import type { CellSelection } from '../../state/AppState';

export function Swatch({ cls }: { cls: CellClass }) {
  return <svg width="22" height="16" aria-hidden="true"><rect className={`hm-cell hm-${cls}`} x="1" y="1" width="20" height="14" rx="3" /></svg>;
}

interface Props { grid: Grid; facets: Record<string, string>; coverage: Coverage; selection: CellSelection | null; onPick: (sel: CellSelection) => void }

export function Heatmap({ grid: g, facets, coverage, selection, onPick }: Props) {
  const v = gridView(g, facets);
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<{ left: number; top: number; content: ReactNode } | null>(null);
  if (!v) return null;
  const L = heatmapLayout(g);
  const { W, H, mt, mr, cw, ch, nx, ny, nrY, ml, colX, rowY } = L;
  const sel = new Set((selection && selection.grid === g.key ? selection.cells : []).map(([x, y]) => `${x},${y}`));
  const gaps = v.gaps || [];

  const showTip = (cell: Cell, node: SVGGElement, ev?: ReactMouseEvent) => {
    const svg = svgRef.current; if (!svg) return;
    const box = svg.getBoundingClientRect(), rect = node.getBoundingClientRect();
    const outcomes = Object.entries(cell.outcomes || {}).map(([k, n]) => `${k} ${count(n)}`).join(', ');
    const px = (ev?.clientX ?? rect.left + rect.width / 2) - box.left, py = (ev?.clientY ?? rect.bottom) - box.top;
    setTip({
      left: Math.max(0, Math.min(px + 14, box.width - 300)), top: py + 14,
      content: <>
        <strong>{binText(g.x, g.x.bins[cell.x])} · {binText(g.y, g.y.bins[cell.y])}</strong><br />
        {count(cell.observed)} run{cell.observed === 1 ? '' : 's'}{outcomes ? ` (${outcomes})` : ''}
        {cell.planned ? <><br />{count(cell.planned)} planned test{cell.planned === 1 ? '' : 's'}, not runs</> : null}
        <br /><span className="muted">{CLASS_LABEL[cell.class]} · click for details</span>
      </>,
    });
  };

  const cells: ReactNode[] = [];
  for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
    const cell = cellAt(v, i, j), x = colX(i), y = rowY(j);
    const dark = cell.class === 'strong';
    const pickCell = () => onPick({ grid: g.key, cells: [[i, j]] });
    cells.push(
      <g key={`${i},${j}`} className={`hm-hit${sel.has(`${i},${j}`) ? ' selected' : ''}`} tabIndex={0} role="button" aria-label={cellSummary(g, cell)}
        onMouseMove={e => showTip(cell, e.currentTarget, e)} onFocus={e => showTip(cell, e.currentTarget)}
        onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)} onClick={pickCell}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pickCell(); } }}>
        <rect className={`hm-cell hm-${cell.class}`} x={(x + 1).toFixed(1)} y={(y + 1).toFixed(1)} width={(cw - 2).toFixed(1)} height={(ch - 2).toFixed(1)} rx="4" />
        {cell.observed ? <text className={`hm-count${dark ? ' on-dark' : ''}`} x={(x + cw / 2).toFixed(1)} y={(y + ch / 2 + 5).toFixed(1)} textAnchor="middle">{count(cell.observed)}</text> : null}
        {cell.planned ? <text className={`hm-planned-count${dark ? ' on-dark' : ''}`} x={(x + cw - 5).toFixed(1)} y={(y + ch - 6).toFixed(1)} textAnchor="end">◇{count(cell.planned)}</text> : null}
      </g>,
    );
  }
  const xLabels = g.x.bins.map((b, i) => {
    const cx = (colX(i) + cw / 2).toFixed(1);
    return <text key={b.key} x={cx} y={mt + ny * ch + nrY + 16} textAnchor="middle">{xLabelLines(b.label, cw).map((l, k) => <tspan key={k} x={cx} dy={k ? 14 : 0}>{l}</tspan>)}</text>;
  });
  const yLabels = g.y.bins.map((b, j) => <text key={b.key} x={ml - 8} y={(rowY(j) + ch / 2 + 4).toFixed(1)} textAnchor="end">{binText(g.y, b)}</text>);
  const t = v.totals;

  const gapGroup = (title: string, status: GridGap['status']) => {
    const items = gaps.map((gp, k) => [gp, k] as const).filter(([gp]) => gp.status === status);
    if (!items.length) return null;
    return <>
      {title ? <h4>{title}</h4> : null}
      <ul className="gap-list">{items.map(([gp, k]) => (
        <li key={k}><button type="button" className={`gap-pick${selection?.grid === g.key && selection.gap === k ? ' active' : ''}`}
          onClick={() => onPick({ grid: g.key, cells: gp.cells, gap: k })}>
          <strong>{gp.label}</strong>{gp.detail ? <span className="muted"> · {gp.detail}</span> : null}
        </button></li>
      ))}</ul>
    </>;
  };

  return (
    <>
      <p className="small" style={{ margin: '0 0 4px' }}><strong>{count(t.observed)} runs</strong> in {count(t.cells_with_runs)} of {count(t.cells)} cells{g.has_planned ? <> · <strong>{count(t.planned)} planned tests</strong></> : null}</p>
      <p className="y-axis-title">↑ {axisTitle(g.y)}</p>
      <div className="chart-wrap">
        <svg ref={svgRef} className="chart heatmap" viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${g.label} coverage heatmap: ${g.y.label} by ${g.x.label}`}>
          {cells}{xLabels}{yLabels}
          <text className="axis-title" x={(ml + W - mr) / 2} y={H - 8} textAnchor="middle">{axisTitle(g.x)}</text>
        </svg>
        <Tooltip tip={tip} id="hm-tip" />
      </div>
      <div className="legend" aria-label="Legend">
        {CELL_CLASSES.filter(k => g.has_planned || k !== 'planned').map(k => (
          <span key={k}><Swatch cls={k} /><strong>{CLASS_LABEL[k]}</strong> <span className="muted">{coverage.cell_classes?.[k] || ''}{k === 'planned' ? ' · ◇ = planned tests in a cell' : ''}</span></span>
        ))}
      </div>
      {gaps.length ? (
        <section className="gaps"><h3>Possible experimental gaps</h3><p className="muted small">Condition ranges with no runs in this collection. Click one to highlight it.</p>
          {g.has_planned ? <>{gapGroup('Planned, not yet run', 'planned')}{gapGroup('Neither run nor planned', 'unplanned')}</> : gapGroup('', 'unplanned')}
        </section>
      ) : null}
      {(g.notes || []).length ? <ul className="hint" style={{ marginTop: 12, paddingLeft: 18 }}>{g.notes!.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
    </>
  );
}
