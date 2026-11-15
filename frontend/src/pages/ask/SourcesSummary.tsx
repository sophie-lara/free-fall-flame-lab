import { docLink, invName } from '../../lib/format';
import { isTableHit, isVisualCrop } from '../../lib/ask';
import type { SearchResult } from '../../lib/types';
import { TableDataSection } from './TableData';

/** Reviewed table data first, then the passages searched (folded under an answer). */
export function SourcesSummary({ results, fold = false }: { results?: SearchResult[]; fold?: boolean }) {
  if (!results?.length) return null;
  const tableHits = results.filter(isTableHit);
  const passages = results.filter(r => !isTableHit(r));
  const tableData = <TableDataSection hits={tableHits} />;
  if (!passages.length) return tableData;
  const docs = new Set(passages.map(r => r.source_id));
  const head = <><h3>Sources searched</h3><span className="muted small">{passages.length} passages · {docs.size} document{docs.size === 1 ? '' : 's'}</span></>;
  const list = (
    <ul className="source-list">
      {passages.map((r, i) => (
        <li key={`${r.chunk_id}-${i}`}>
          <div className="row">
            <strong>{r.filename}</strong>
            {r.record_card ? <span className="pill ok">Table record · {r.record_card.review_action}</span> : <span className="pill">page {r.physical_page}</span>}
            {r.visual ? <span className="pill warn">{r.visual.kind} {r.visual.label} · AI description</span> : null}
            {r.investigation_id ? <span className="pill">{invName(r.investigation_id)}</span> : null}
            <span className="spacer" />
            {r.record_card
              ? <span className="small muted">{r.record_card.locator || ''}</span>
              : <a className="small" href={docLink(r.source_id, r.physical_page)} target="_blank" rel="noopener noreferrer">Open page ↗</a>}
          </div>
          <div className="muted small">{String(r.visual ? r.visual.caption : r.text || '').replace(/\s+/g, ' ').slice(0, 220)}…</div>
          {isVisualCrop(r) ? <img className="crop result-thumb" loading="lazy" src={String(r.crop_url)} alt={`Original page image for ${r.visual!.kind} ${r.visual!.label}`} /> : null}
        </li>
      ))}
    </ul>
  );
  return (
    <>
      {tableData}
      {fold
        ? <details className="card sources-card"><summary className="section-head">{head}</summary>{list}</details>
        : <section className="card sources-card"><div className="section-head">{head}</div>{list}</section>}
    </>
  );
}
