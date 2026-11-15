import { describe, expect, it } from 'vitest';
import { axisSpan, axisTitle, binText, cellAt, cellSummary, gridView, heatmapLayout, viewKey, xLabelLines } from './coverage';
import type { Axis, Grid } from './types';

const x: Axis = { key: 'oxygen_pct', label: 'Initial oxygen', unit: '% vol', bins: [
  { key: '10-15', label: '10–15', lo: 10, hi: 15 }, { key: '15-20', label: '15–20', lo: 15, hi: 20 }, { key: 'Not recorded', label: 'Not recorded', lo: null, hi: null }] };
const y: Axis = { key: 'material', label: 'Sample material', unit: null, bins: [
  { key: 'rod', label: 'PMMA rod', lo: null, hi: null }, { key: 'film', label: 'PMMA film', lo: null, hi: null }] };
const grid: Grid = {
  key: 'bass', label: 'BASS', description: '', x, y, has_planned: false, notes: [],
  facets: [{ key: 'fuel', label: 'Fuel', options: [] }, { key: 'dil', label: 'Diluent', options: [] }],
  views: { 'fuel=all|dil=all': { cells: [{ x: 0, y: 1, ids: ['a'], planned_ids: [], outcomes: {}, reviewed: 0, observed: 1, planned: 2, neighbours: 0, class: 'sparse' }], totals: { observed: 1, planned: 0, cells_with_runs: 1, cells: 6 } } },
};

describe('coverage helpers', () => {
  it('builds the view key from facets', () => {
    expect(viewKey(grid)).toBe('fuel=all|dil=all');
    expect(viewKey(grid, { fuel: 'C7H16' })).toBe('fuel=C7H16|dil=all');
    expect(viewKey({ ...grid, facets: [] })).toBe('all');
    expect(gridView(grid).cells).toHaveLength(1);
  });
  it('formats bins and axes', () => {
    expect(binText(x, x.bins[0])).toBe('10–15 % vol');
    expect(binText(x, x.bins[2])).toBe('Not recorded');
    expect(axisTitle(x)).toBe('Initial oxygen (% vol)');
    expect(axisTitle(y)).toBe('Sample material');
  });
  it('fills missing cells as gaps', () => {
    const v = gridView(grid);
    expect(cellAt(v, 0, 1).observed).toBe(1);
    expect(cellAt(v, 1, 0)).toMatchObject({ x: 1, y: 0, class: 'gap', observed: 0, ids: [] });
  });
  it('summarises a cell for screen readers', () => {
    expect(cellSummary(grid, cellAt(gridView(grid), 0, 1))).toBe('Initial oxygen 10–15 % vol, sample material PMMA film: 1 run, 2 planned tests. Sparse.');
  });
  it('describes a gap band by its range', () => {
    expect(axisSpan(x, [1, 0, 1])).toBe('Initial oxygen 10–20 % vol');
    expect(axisSpan(y, [1, 0])).toBe('PMMA rod, PMMA film');
  });
  it('sets "Not recorded" apart', () => {
    const L = heatmapLayout(grid);
    expect(L.colX(2) - L.colX(1)).toBeCloseTo(L.cw + 14);
    expect(L.colX(1) - L.colX(0)).toBeCloseTo(L.cw);
    expect(L.nrY).toBe(0);
  });
  it('wraps long x labels onto two lines', () => {
    expect(xLabelLines('Not recorded', 40)).toEqual(['Not', 'recorded']);
    expect(xLabelLines('10–15', 80)).toEqual(['10–15']);
  });
});
