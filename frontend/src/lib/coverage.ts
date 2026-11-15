// Coverage heatmap helpers. Bins and cell classes come from the server.
import { count } from './format';
import type { Axis, Bin, Cell, CellClass, Grid, GridView } from './types';

export const CELL_CLASSES: CellClass[] = ['strong', 'moderate', 'sparse', 'planned', 'gap'];
export const CLASS_LABEL: Record<CellClass, string> = { strong: 'Strong', moderate: 'Moderate', sparse: 'Sparse', planned: 'Planned only', gap: 'Gap' };
export const NOT_RECORDED = 'Not recorded';

export type Facets = Record<string, Record<string, string>>;

export const viewKey = (g: Grid, facets: Record<string, string> = {}): string =>
  g.facets.length ? g.facets.map(x => `${x.key}=${facets[x.key] || 'all'}`).join('|') : 'all';

export const gridView = (g: Grid, facets: Record<string, string> = {}): GridView => g.views[viewKey(g, facets)];

export const binText = (axis: Axis, b: Bin): string => (b.lo != null && axis.unit ? `${b.label} ${axis.unit}` : b.label);
export const axisTitle = (axis: Axis): string => `${axis.label}${axis.unit ? ` (${axis.unit})` : ''}`;

export function cellAt(v: GridView, i: number, j: number): Cell {
  return v.cells.find(c => c.x === i && c.y === j)
    || { x: i, y: j, observed: 0, planned: 0, neighbours: 0, class: 'gap', ids: [], planned_ids: [], outcomes: {}, reviewed: 0 };
}

export function cellSummary(g: Grid, c: Cell): string {
  const runs = `${count(c.observed)} run${c.observed === 1 ? '' : 's'}`;
  const planned = c.planned ? `, ${count(c.planned)} planned test${c.planned === 1 ? '' : 's'}` : '';
  return `${axisTitle(g.x).split(' (')[0]} ${binText(g.x, g.x.bins[c.x])}, ${g.y.label.toLowerCase()} ${binText(g.y, g.y.bins[c.y])}: ${runs}${planned}. ${CLASS_LABEL[c.class]}.`;
}

/** A gap band is described by its overall range on each axis, not cell by cell. */
export function axisSpan(axis: Axis, idx: number[]): string {
  const bins = [...new Set(idx)].sort((a, b) => a - b).map(k => axis.bins[k]);
  return bins.every(b => b.lo != null)
    ? `${axis.label} ${bins[0].lo}–${bins[bins.length - 1].hi}${axis.unit ? ` ${axis.unit}` : ''}`
    : bins.map(b => b.label).join(', ');
}

export interface HeatmapLayout {
  W: number; H: number; mt: number; mr: number; mb: number; ml: number;
  cw: number; ch: number; nx: number; ny: number; nrY: number;
  colX: (i: number) => number;
  rowY: (j: number) => number;
}

/** Geometry of the heatmap; "Not recorded" bins sit apart from the real ranges. */
export function heatmapLayout(g: Grid): HeatmapLayout {
  const nx = g.x.bins.length, ny = g.y.bins.length;
  const longest = Math.max(...g.y.bins.map(b => binText(g.y, b).length));
  const W = 880, mt = 8, mr = 8, mb = 64, ml = Math.min(230, Math.max(84, longest * 7 + 36));
  const SEP = 14;
  const nrX = g.x.bins.some(b => b.key === NOT_RECORDED) ? SEP : 0;
  const nrY = g.y.bins.some(b => b.key === NOT_RECORDED) ? SEP : 0;
  const cw = (W - ml - mr - nrX) / nx, ch = Math.max(34, Math.min(50, 400 / ny)), H = mt + ny * ch + nrY + mb;
  const colX = (i: number) => ml + i * cw + (g.x.bins[i].key === NOT_RECORDED ? nrX : 0);
  const nrRow = g.y.bins.findIndex(b => b.key === NOT_RECORDED); // drawn on top; rows below it shift down
  const rowY = (j: number) => mt + (ny - 1 - j) * ch + (nrRow >= 0 && j < nrRow ? nrY : 0);
  return { W, H, mt, mr, mb, ml, cw, ch, nx, ny, nrY, colX, rowY };
}

/** Splits a long x-axis bin label over two lines when it does not fit the column. */
export function xLabelLines(label: string, cw: number): string[] {
  const words = label.length * 6.6 > cw - 4 ? label.split(' ') : [label];
  const half = Math.ceil(words.length / 2);
  return words.length > 1 ? [words.slice(0, half).join(' '), words.slice(half).join(' ')] : words;
}
