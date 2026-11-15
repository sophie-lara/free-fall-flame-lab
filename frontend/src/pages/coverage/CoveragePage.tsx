// Explore → Experiment coverage: one heatmap per investigation family.
import { useEffect, useRef } from 'react';
import { EmptyBox, PageHead } from '../../components/common';
import { useApp } from '../../state/AppState';
import type { CellSelection } from '../../state/AppState';
import { scrollBehavior } from '../../lib/format';
import type { Grid } from '../../lib/types';
import { CellDetail, RecordDetail } from './Details';
import { Heatmap } from './Heatmap';

const LEAD = 'Where have experiments actually been run? Each heatmap cell counts the runs whose test conditions fall in that range. Empty cells are conditions with no runs in this collection.';

export function CoveragePage() {
  const { coverage, coverageError, cov, setCov } = useApp();
  const cellRef = useRef<HTMLDivElement>(null);
  const pickNonce = useRef(0);
  const lastScrolled = useRef(0);

  const grids = coverage?.grids || [];
  const g: Grid | undefined = grids.find(x => x.key === cov.grid) || grids[0];
  const facets = g ? cov.facets[g.key] || {} : {};

  useEffect(() => {
    if (pickNonce.current === lastScrolled.current) return;
    lastScrolled.current = pickNonce.current;
    cellRef.current?.scrollIntoView({ behavior: scrollBehavior(), block: 'nearest' });
  });

  const head = <PageHead eyebrow="Explore" title="Experiment coverage" lead={LEAD} />;
  if (!coverage && !coverageError) return <div id="explore-cov"><p className="loading">Loading experiment coverage…</p></div>;
  if (coverageError) return <div id="explore-cov">{head}<EmptyBox title="Not available yet" text={coverageError} /></div>;
  if (!g) return <div id="explore-cov">{head}<EmptyBox title="Not available yet" text="Experiment coverage is being prepared and is not available yet." /></div>;

  const pick = (sel: CellSelection) => { pickNonce.current += 1; setCov({ cell: sel, detail: null }); };

  return (
    <div id="explore-cov">
      {head}
      <section className="card">
        <div className="controls">
          <div className="field"><label>Investigation family</label>
            <div className="segmented" role="group" aria-label="Investigation family">
              {grids.map(x => <button key={x.key} type="button" aria-pressed={x.key === g.key} onClick={() => setCov({ grid: x.key, cell: null, detail: null })}>{x.label}</button>)}
            </div>
          </div>
          {g.facets.map(f => (
            <div className="field" key={f.key}><label htmlFor={`facet-${f.key}`}>{f.label}</label>
              <select id={`facet-${f.key}`} value={facets[f.key] || 'all'} onChange={e => {
                const value = e.target.value;
                setCov(c => ({
                  facets: { ...c.facets, [g.key]: { ...(c.facets[g.key] || {}), [f.key]: value } },
                  detail: null,
                  cell: c.cell?.gap != null ? null : c.cell,
                }));
              }}>
                {f.options.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
              </select>
            </div>
          ))}
          <span className="spacer" />
        </div>
        <p className="muted" style={{ margin: '0 0 12px' }}>{g.description}</p>
        <div id="cov-view"><Heatmap grid={g} facets={facets} coverage={coverage!} selection={cov.cell} onPick={pick} /></div>
      </section>
      <div id="cov-cell" className="section" aria-live="polite" ref={cellRef}>
        <CellDetail grid={g} facets={facets} coverage={coverage!} selection={cov.cell}
          onClose={() => setCov({ cell: null, detail: null })} onOpenRun={id => setCov({ detail: id })} />
      </div>
      <div id="cov-detail" aria-live="polite">
        <RecordDetail coverage={coverage!} id={cov.detail} onClose={() => setCov({ detail: null })} />
      </div>
    </div>
  );
}
