// Reviewed table data: table cards and exact-value rows, with value notes.
import { count, docLink, prettyField } from '../../lib/format';
import type { Note, SearchResult } from '../../lib/types';

export const NOTE_MARK: Record<string, string> = { ambiguous: '◐', unresolved: '?', pending: '…', assumed: '≈', inferred: '≈', definition: 'i' };
export const NOTE_LABEL: Record<string, string> = { ambiguous: 'Ambiguous', unresolved: 'Unresolved', pending: 'Pending', assumed: 'Assumed', inferred: 'Inferred', definition: 'Definition' };
const EVIDENCE: Record<string, [string, string]> = {
  run: ['Observed run', 'ok'],
  background_table_row: ['Background data · not a run', ''],
  planned_test_condition: ['Proposed test · not run as listed', 'warn'],
};

export function EvidencePill({ kind }: { kind?: string }) {
  const [label, cls] = (kind && EVIDENCE[kind]) || ['Table data', ''];
  return <span className={`pill ${cls}`}>{label}</span>;
}

export const visibleNotes = (notes?: Note[]): Note[] => (notes || []).filter(n => n.kind !== 'model');
const noteLabel = (kind: string) => NOTE_LABEL[kind] || kind;

function NoteMarks({ notes }: { notes?: Note[] }) {
  return <>{visibleNotes(notes).map((n, i) => (
    <span key={i} className={`note-mark note-${n.kind}`} tabIndex={0} title={`${noteLabel(n.kind)}: ${n.text}`} aria-label={`${noteLabel(n.kind)} note: ${n.text}`}>{NOTE_MARK[n.kind] || '•'}</span>
  ))}</>;
}

function TableSourceLink({ r, label }: { r: SearchResult; label: string }) {
  return r.source_id ? <a className="small" href={docLink(r.source_id, r.physical_page || null)} target="_blank" rel="noopener noreferrer">{label} ↗</a> : null;
}
function Caveats({ items }: { items?: string[] }) {
  return items?.length ? <ul className="caveats">{items.map((t, i) => <li key={i}>{t}</li>)}</ul> : null;
}

/** Visible notes across a row's values, deduplicated by kind and text, each with its field. */
export function rowNotes(values: { field: string; notes?: Note[] }[]): (Note & { field: string })[] {
  const notes: (Note & { field: string })[] = [];
  values.forEach(v => visibleNotes(v.notes).forEach(n => { if (!notes.some(x => x.kind === n.kind && x.text === n.text)) notes.push({ ...n, field: v.field }); }));
  return notes;
}

function RowHit({ r }: { r: SearchResult }) {
  const c = r.record_card!;
  const values = c.values || [];
  const notes = rowNotes(values);
  const modelNotes = values.flatMap(v => (v.notes || []).filter(n => n.kind === 'model').map(n => `${prettyField(v.field)}: ${n.text}`));
  return (
    <article className="table-hit">
      <div className="row"><span className="pill ok">Table row</span><EvidencePill kind={c.evidence_kind} /><strong>{c.test_id}</strong><span className="muted small">{c.table_title || ''}</span><span className="spacer" /><TableSourceLink r={r} label={r.physical_page ? `Open page ${r.physical_page}` : 'Open source table'} /></div>
      {c.provenance ? <p className="provenance">{c.provenance}</p> : null}
      {(c.match || []).length
        ? <p className="small" style={{ margin: '6px 0' }}>Matched your values: {c.match!.map((m, i) => (
          <span key={i}>{i ? ' · ' : ''}<strong>{m.query}</strong> → {prettyField(m.field)}{m.conversion ? <> <span className="pill warn">{m.conversion}</span></> : null}</span>
        ))}</p>
        : <p className="small muted" style={{ margin: '6px 0' }}>Named by its test ID in your question.</p>}
      <Caveats items={c.caveats} />
      <div className="table-scroll"><table className="row-values"><thead><tr><th>Field</th><th>Value</th><th>As printed in the source</th></tr></thead><tbody>
        {values.map((v, i) => <tr key={i}><td>{prettyField(v.field)}</td><td>{String(v.value ?? '—')}{v.unit ? ` ${v.unit}` : ''} <NoteMarks notes={v.notes} /></td><td className="muted">{v.original ?? ''}</td></tr>)}
      </tbody></table></div>
      {notes.length ? <ul className="note-list">{notes.map((n, i) => <li key={i}><span className={`note-mark note-${n.kind}`} aria-hidden="true">{NOTE_MARK[n.kind] || '•'}</span><strong>{noteLabel(n.kind)}</strong> ({prettyField(n.field)}): {n.text}</li>)}</ul> : null}
      {modelNotes.length ? <details className="small"><summary>All notes, including the model's</summary><ul>{modelNotes.map((t, i) => <li key={i}>{t}</li>)}</ul></details> : null}
      <p className="muted small" style={{ margin: '4px 0 0' }}>{c.locator || ''}</p>
    </article>
  );
}

function TableHit({ r }: { r: SearchResult }) {
  const c = r.record_card!;
  const kinds = Object.keys(c.evidence_kinds || {});
  const rows = c.rows ?? 0;
  return (
    <article className="table-hit">
      <div className="row"><span className="pill ok">Table</span>{kinds.map(k => <EvidencePill key={k} kind={k} />)}<strong>{c.table_title}</strong><span className="muted small">{count(c.rows)} row{rows === 1 ? '' : 's'}</span><span className="spacer" /><TableSourceLink r={r} label="Open source table" /></div>
      {c.provenance ? <p className="provenance">{c.provenance}</p> : null}
      <Caveats items={c.caveats} />
      {(c.notes || []).length ? <ul className="note-list">{c.notes!.slice(0, 4).map((n, i) => <li key={i}><span className={`note-mark note-${n.kind}`} aria-hidden="true">{NOTE_MARK[n.kind] || '•'}</span><strong>{noteLabel(n.kind)}</strong> ({count(n.rows)} of {count(c.rows)} rows): {n.text}</li>)}</ul> : null}
      <p className="muted small" style={{ margin: '4px 0 0' }}>{c.locator || ''}. To see individual rows, include two or more of a row's exact values in your question.</p>
    </article>
  );
}

export function TableDataSection({ hits }: { hits: SearchResult[] }) {
  if (!hits.length) return null;
  const rows = hits.filter(r => r.record_card?.kind === 'row');
  const tables = hits.length - rows.length;
  return (
    <section className="card stack">
      <div className="section-head"><h3>Reviewed table data</h3><span className="muted small">{rows.length ? `${rows.length} matching row${rows.length === 1 ? '' : 's'} · ` : ''}{tables} table{tables === 1 ? '' : 's'}</span></div>
      <p className="muted small" style={{ margin: 0 }}>Values transcribed from NASA tables and reviewed. Marks beside a value (◐ ambiguous, ? unresolved, ≈ assumed or inferred, i definition) carry a note; hover or tap them.</p>
      {hits.map((r, i) => (r.record_card?.kind === 'row' ? <RowHit key={i} r={r} /> : <TableHit key={i} r={r} />))}
    </section>
  );
}
