// Coverage: the selected cell or gap band, and a single run's record.
import { Fragment } from 'react';
import type { KeyboardEvent, MouseEvent, ReactNode } from 'react';
import { CLASS_LABEL, axisSpan, binText, cellAt, gridView } from '../../lib/coverage';
import { count, docLink, fmt, invName, safeURL } from '../../lib/format';
import type { Cell, Coverage, CoverageRecord, Grid, ProposedTest } from '../../lib/types';
import type { CellSelection } from '../../state/AppState';
import { Swatch } from './Heatmap';

function ExtLink({ url, text }: { url?: string | null; text: string }) {
  return url ? <a href={safeURL(url)} target="_blank" rel="noopener noreferrer">{text} ↗</a> : <>{text}</>;
}

export function RunSource({ r }: { r: CoverageRecord }) {
  return <><ExtLink url={r.source?.url} text={`NASA ${r.investigation_id}`} /><br /><span className="muted">{r.source?.file || ''}{r.source?.record != null ? `, record ${r.source.record}` : ''}</span></>;
}

function PlannedSource({ p }: { p: ProposedTest }) {
  const label = `EIRD Table ${p.table}, page ${p.page}`;
  return <>
    {p.document_id ? <a href={docLink(p.document_id, p.page)} target="_blank" rel="noopener noreferrer">{label} ↗</a> : label}
    {p.source_url ? <><br /><ExtLink url={p.source_url} text={`NASA ${p.investigation_id}`} /></> : null}
  </>;
}

const FUELS: Record<string, string> = { C7H16: 'Heptane (C₇H₁₆)', CH3OH: 'Methanol (CH₃OH)' };
type Col = [string, (r: CoverageRecord) => string | null | undefined, boolean?];

interface CellProps { grid: Grid; facets: Record<string, string>; coverage: Coverage; selection: CellSelection | null; onClose: () => void; onOpenRun: (id: string) => void }

export function CellDetail({ grid: g, facets, coverage, selection, onClose, onOpenRun }: CellProps) {
  if (!selection || selection.grid !== g.key) return null;
  const v = gridView(g, facets);
  if (!v) return null;
  const members = selection.cells.map(([x, y]) => cellAt(v, x, y));
  const gap = selection.gap != null ? (v.gaps || [])[selection.gap] : null;
  if (selection.gap != null && !gap) return null;
  const cell: Cell = members.length === 1 ? members[0] : {
    x: members[0]?.x ?? 0, y: members[0]?.y ?? 0, ids: members.flatMap(m => m.ids), planned_ids: members.flatMap(m => m.planned_ids), outcomes: {},
    observed: 0, planned: members.reduce((n, m) => n + m.planned, 0), neighbours: 0, reviewed: 0, class: gap?.status === 'planned' ? 'planned' : 'gap',
  };
  const byId = Object.fromEntries(coverage.records.map(r => [String(r.id), r]));
  const runs = cell.ids.map(id => byId[String(id)]).filter(Boolean);
  const outcomeOf = (r: CoverageRecord) => r.raw?.['Test end'] || (r.outcomes?.burn_time_s?.raw ? `burn time ${r.outcomes.burn_time_s.raw}` : '');
  const cols = ([
    ['Material', r => r.raw?.['Fuel Sample Material'] || r.material],
    ['O₂ (%)', r => (r.oxygen_pct != null ? fmt(r.oxygen_pct) : null), true],
    ['Pressure (atm)', r => (r.pressure_kpa ? fmt(r.pressure_kpa / 101.325) : null), true],
    ['Flow (cm/s)', r => (r.flow_cm_s != null ? fmt(r.flow_cm_s) : null), true],
    ['Outcome', outcomeOf],
  ] as Col[]).filter(([, f]) => runs.some(r => f(r)));

  const open = (e: MouseEvent | KeyboardEvent, id: string) => {
    if (e.target instanceof Element && e.target.closest('a')) return;
    onOpenRun(id);
  };
  const runTable = runs.length ? (
    <div className="table-scroll" style={{ maxHeight: 360 }}><table><thead><tr><th>Run</th><th>Investigation</th>{cols.map(([h, , n]) => <th key={h} className={n ? 'num' : undefined}>{h}</th>)}<th>Source</th></tr></thead><tbody>
      {runs.map(r => (
        <tr key={r.id} tabIndex={0} style={{ cursor: 'pointer' }} onClick={e => open(e, r.id)} onKeyDown={e => { if (e.key === 'Enter') open(e, r.id); }}>
          <td>{r.test_id}{r.review_status === 'reviewed' ? <> <span className="pill ok">Reviewed</span></> : null}</td>
          <td>{invName(r.investigation_id)}</td>
          {cols.map(([h, f, n]) => <td key={h} className={n ? 'num' : undefined}>{f(r) || '—'}</td>)}
          <td className="small"><RunSource r={r} /></td>
        </tr>
      ))}
    </tbody></table></div>
  ) : <p className="muted">No runs in this collection fall in {gap ? 'this range' : 'this cell'}.</p>;

  const proposed = cell.planned_ids.map(i => coverage.proposed?.[i]).filter((p): p is ProposedTest => !!p);
  const plannedTable = proposed.length ? <>
    <h4 style={{ margin: '20px 0 8px' }}>Planned tests · {count(proposed.length)}</h4>
    <p className="muted small" style={{ margin: '0 0 8px' }}>From the FLEX EIRD test matrices: planned conditions, not runs, with no results.</p>
    <div className="table-scroll" style={{ maxHeight: 300 }}><table><thead><tr><th>Test</th><th>Source</th><th>Fuel</th><th>Added diluent</th><th className="num">O₂ (%)</th><th className="num">Pressure (atm)</th></tr></thead><tbody>
      {proposed.map((p, i) => (
        <tr key={`${p.test_id}-${i}`}><td>{p.test_id}</td><td className="small"><PlannedSource p={p} /></td><td>{(p.fuel && FUELS[p.fuel]) || p.fuel || '—'}</td><td>{p.suppressant || 'none'}</td>
          <td className="num">{fmt(p.fields?.oxygen_pct)}</td><td className="num">{p.fields?.pressure_kpa != null ? fmt(p.fields.pressure_kpa / 101.325) : '—'}</td></tr>
      ))}
    </tbody></table></div>
  </> : null;

  const outcomes = Object.entries(cell.outcomes || {});
  const title = gap ? gap.label : `${g.x.label} ${binText(g.x, g.x.bins[cell.x])} · ${g.y.label} ${binText(g.y, g.y.bins[cell.y])}`;
  const pill = gap
    ? <span className="pill">Possible gap · {gap.status === 'planned' ? 'planned, not run' : 'not planned'}</span>
    : <span className="pill"><Swatch cls={cell.class} />{CLASS_LABEL[cell.class]}</span>;
  const sub = gap
    ? `${axisSpan(g.x, members.map(m => m.x))} · ${axisSpan(g.y, members.map(m => m.y))}${gap.planned ? ` · ${count(gap.planned)} planned test${gap.planned === 1 ? '' : 's'}, no runs` : ' · no runs or planned tests'}`
    : coverage.cell_classes?.[cell.class] || '';
  return (
    <section className="card">
      <div className="row"><h3 style={{ margin: 0 }}>{title}</h3>{pill}<span className="spacer" /><button className="btn small" type="button" id="close-cell" onClick={onClose}>Close</button></div>
      <p className="muted small" style={{ margin: '8px 0 16px' }}>{sub}</p>
      {gap ? null : <>
        <h4 style={{ margin: '0 0 8px' }}>Runs · {count(runs.length)}</h4>
        {outcomes.length ? <p className="small" style={{ margin: '0 0 8px' }}>Outcomes: {outcomes.map(([k, n]) => `${k} ${count(n)}`).join(' · ')}</p> : null}
        {runTable}
      </>}
      {plannedTable}
    </section>
  );
}

export function RecordDetail({ coverage, id, onClose }: { coverage: Coverage; id: string | null; onClose: () => void }) {
  const r = id == null ? undefined : coverage.records.find(x => String(x.id) === String(id));
  if (!r) return null;
  const familyLabel = (coverage.families || []).find(f => f.key === r.family)?.label || r.family;
  const row = (k: string, v: ReactNode) => (v == null || v === '' ? null : <><dt>{k}</dt><dd>{v}</dd></>);
  const outcomes = Object.entries(r.outcomes || {});
  return (
    <section className="card">
      <div className="row"><h3 style={{ margin: 0 }}>{familyLabel} · {r.test_id}</h3>{r.review_status === 'reviewed' ? <span className="pill ok">Reviewed</span> : null}<span className="spacer" /><button className="btn small" type="button" id="close-detail" onClick={onClose}>Close</button></div>
      <dl className="kv" style={{ marginTop: 16 }}>
        {row('Investigation', invName(r.investigation_id))}
        {row('Material', r.material)}
        {row('Geometry', r.geometry)}
        {row('Oxygen', r.oxygen_pct != null ? `${fmt(r.oxygen_pct)} %` : null)}
        {row('Flow', r.flow_cm_s != null ? `${fmt(r.flow_cm_s)} cm/s` : null)}
        {row('Pressure', r.pressure_kpa != null ? `${fmt(r.pressure_kpa)} kPa` : null)}
        {row('Gravity', r.gravity)}
        {outcomes.map(([k, o]) => <Fragment key={k}>{row(k.replaceAll('_', ' '), <>{o.value != null ? fmt(o.value) : '—'}{o.unit ? ` ${o.unit}` : ''} <span className="muted small">(source text: “{o.raw}”)</span></>)}</Fragment>)}
        {row('Source', <RunSource r={r} />)}
      </dl>
    </section>
  );
}
