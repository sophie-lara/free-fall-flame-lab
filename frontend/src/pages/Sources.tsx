// Sources, organized by the three kinds of fire NASA studied in orbit.
import { PageHead } from '../components/common';
import { useApp } from '../state/AppState';
import { count, docLink, fmt, invName, psiLink, safeURL, scrollBehavior } from '../lib/format';
import type { CorpusDocument, Coverage, CoverageRecord } from '../lib/types';

export const EXPERIMENT_TYPES = [
  { key: 'bass', grid: 'bass', title: 'BASS and BASS-II: burning solid materials', investigations: ['PSI-26', 'PSI-25'], families: ['bass', 'bass-ii'],
    text: 'Burning and Suppression of Solids. Small samples of solid materials, such as PMMA plastic rods and sheets and cotton-fiberglass fabric, were burned in a small flow duct inside the International Space Station’s Microgravity Science Glovebox. Crews varied airflow, oxygen and sample shape to see how flames spread, how they go out, and how readily materials burn without gravity.' },
  { key: 'flex', grid: 'flex', title: 'FLEX: burning fuel droplets', investigations: ['PSI-69', 'PSI-68'], families: ['flex'],
    text: 'Flame Extinguishment Experiment. Single droplets of liquid fuel, such as heptane and methanol, free-floating or held on a thin fiber, were ignited in the station’s Combustion Integrated Rack. Without buoyancy the flame forms a sphere around the droplet, which makes it possible to measure burning rates, extinction, and the effect of diluent gases such as helium and carbon dioxide.' },
  { key: 'saffire', grid: 'saffire', title: 'Saffire: spacecraft-scale fires', investigations: ['SAFFIRE', 'PSI-98', 'PSI-99', 'PSI-100'], families: ['saffire'],
    text: 'Spacecraft Fire Safety Demonstration. Large material samples were burned inside uncrewed Cygnus cargo vehicles after they left the space station, so fire growth could be studied at a realistic spacecraft scale with no risk to crews.' },
];
type ExperimentType = (typeof EXPERIMENT_TYPES)[number];

export const typeOf = (d: CorpusDocument): ExperimentType | undefined =>
  EXPERIMENT_TYPES.find(x => (d.investigation_ids || []).some(i => x.investigations.includes(i)));

function SourceRunsTable({ coverage, records }: { coverage: Coverage; records: CoverageRecord[] }) {
  const fields = (coverage.fields || []).filter(f => records.some(r => Number.isFinite(r[f.key]))).slice(0, 5);
  return (
    <div className="table-scroll"><table><thead><tr><th>Test</th><th>Material</th>{fields.map(f => <th key={f.key} className="num">{f.label}{f.unit ? ` (${f.unit})` : ''}</th>)}<th>Status</th><th>Source table</th></tr></thead><tbody>
      {records.map(r => (
        <tr key={r.id}><td>{r.test_id}</td><td>{r.material || '—'}</td>{fields.map(f => <td key={f.key} className="num">{fmt(r[f.key])}</td>)}
          <td>{r.review_status === 'reviewed' ? <span className="pill ok">Reviewed</span> : <span className="pill">Transcribed</span>}</td><td className="small muted">{r.source?.file || ''}</td></tr>
      ))}
    </tbody></table></div>
  );
}

function DocRow({ d }: { d: CorpusDocument }) {
  const pages = d.pages ?? 0;
  return (
    <li className="doc-row">
      <div className="doc-main"><strong>{d.filename}</strong>
        <span className="muted small">{(d.investigation_ids || []).map(invName).join(', ')} · {count(d.pages)} page{pages === 1 ? '' : 's'}{d.figures ? ` · ${count(d.figures)} figure${d.figures === 1 ? '' : 's'}` : ''}</span></div>
      <div className="row doc-links">
        <a className="small" href={docLink(d.source_id)} target="_blank" rel="noopener noreferrer">Open PDF ↗</a>
        {d.source_url ? <a className="small" href={safeURL(d.source_url)} target="_blank" rel="noopener noreferrer">NASA record ↗</a> : null}
      </div>
    </li>
  );
}

export function Sources() {
  const { corpus, coverage: cov, setCov, askQuestion } = useApp();
  if (!corpus) return <p className="loading">Loading sources…</p>;
  const docs = corpus.documents || [], t = corpus.totals || {};
  const other = docs.filter(d => !typeOf(d));
  const shortName = (x: ExperimentType) => x.title.split(':')[0];

  const section = (x: ExperimentType) => {
    const mine = docs.filter(d => typeOf(d) === x);
    const runs = cov ? cov.records.filter(r => x.families.includes(String(r.family || '').toLowerCase())) : [];
    const reviewed = runs.filter(r => r.review_status === 'reviewed').length;
    const links = x.investigations.filter(i => psiLink(i));
    return (
      <section className="card source-type" id={`src-${x.key}`} aria-labelledby={`src-${x.key}-h`} key={x.key}>
        <h2 id={`src-${x.key}-h`}>{x.title}</h2>
        <p className="source-type-text">{x.text}</p>
        <div className="source-cols">
          <div><h3>Reports <span className="muted small">{count(mine.length)}</span></h3>
            {mine.length ? <ul className="doc-list">{mine.map(d => <DocRow key={d.source_id} d={d} />)}</ul> : <p className="muted small">None indexed.</p>}</div>
          <div><h3>Experiment data</h3>
            {runs.length
              ? <p className="source-stat"><strong>{count(runs.length)}</strong> experiment runs from NASA PSI tables{reviewed ? <>, <strong>{count(reviewed)}</strong> reviewed</> : null}.</p>
              : <p className="muted small">No experiment tables indexed.</p>}
            <div className="row doc-links">
              {runs.length ? <a className="btn small" href="#/coverage" onClick={() => setCov({ grid: x.grid })}>Coverage heatmap →</a> : null}
              <a className="btn small" href="#/ask" onClick={e => { e.preventDefault(); askQuestion(`What did the ${shortName(x)} experiments study and find?`); }}>Ask about {shortName(x)}</a>
            </div>
            {links.length ? <div className="row doc-links" style={{ marginTop: 8 }}>{links.map(i => <a key={i} className="small" href={psiLink(i)} target="_blank" rel="noopener noreferrer">{invName(i)} dataset ↗</a>)}</div> : null}
            {runs.length && cov ? <details className="source-runs"><summary>Experiment runs ({count(runs.length)})</summary><SourceRunsTable coverage={cov} records={runs} /></details> : null}
          </div>
        </div>
      </section>
    );
  };

  return (
    <>
      <PageHead eyebrow="Sources" title="What the atlas draws on" lead={`${count(t.documents || docs.length)} NASA reports and ${count(cov?.records?.length || 0)} experiment runs from three kinds of fire experiments flown in orbit. Every answer links back to these pages and tables.`} />
      <nav className="row source-jump" aria-label="Experiment types">
        {EXPERIMENT_TYPES.map(x => <a key={x.key} className="chip" href="#/sources" onClick={e => { e.preventDefault(); document.getElementById(`src-${x.key}`)?.scrollIntoView({ block: 'start', behavior: scrollBehavior() }); }}>{shortName(x)}</a>)}
      </nav>
      <div className="stack">
        {EXPERIMENT_TYPES.map(section)}
        {other.length ? <section className="card source-type"><h2>Other documents</h2><ul className="doc-list">{other.map(d => <DocRow key={d.source_id} d={d} />)}</ul></section> : null}
      </div>
    </>
  );
}
