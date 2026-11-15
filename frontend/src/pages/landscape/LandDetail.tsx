import { useApp } from '../../state/AppState';
import { docLink, invName } from '../../lib/format';
import { KIND_LABEL } from '../../lib/landscape';
import type { Slots } from '../../lib/landscape';
import type { LandPoint, LandscapeData } from '../../lib/types';

function LandItem({ p }: { p: LandPoint }) {
  return <>
    <strong>{p.label || KIND_LABEL[p.kind]}</strong> · <a href={docLink(p.source_id, p.page)} target="_blank" rel="noopener">{p.filename}{p.page ? `, page ${p.page}` : ''}</a>
    {p.investigation ? <> <span className="muted small">{invName(p.investigation)}</span></> : null}
  </>;
}

interface Props {
  data: LandscapeData; selected: string | null; slots: Slots;
  onClose: () => void; onToggleTopic: (id: number) => void; onSelect: (id: string) => void;
}

export function LandDetail({ data: d, selected, slots, onClose, onToggleTopic, onSelect }: Props) {
  const { askQuestion } = useApp();
  const p = selected ? d.byId[selected] : null;
  if (!p) return null;
  const topic = p.cluster >= 0 ? d.byCluster[p.cluster] : null;
  const related = p.neighbors.map(id => d.byId[id]).filter(Boolean);
  return (
    <section className="card">
      <div className="row"><h3 style={{ margin: 0 }}>{p.label || KIND_LABEL[p.kind]}</h3>{p.kind === 'figure' ? <span className="pill warn">AI figure description</span> : null}<span className="spacer" /><button className="btn small" type="button" id="land-close" onClick={onClose}>Close</button></div>
      <p style={{ marginTop: 12 }}><LandItem p={p} /></p>
      <blockquote className="small">{p.snippet}{p.snippet.length >= 240 ? '…' : ''}</blockquote>
      {topic ? <>
        <p><span className="muted">Topic:</span> <strong>{topic.label}</strong>{p.core ? null : <> <span className="muted small">(loosely)</span></>}{topic.description ? <> · <span className="small">{topic.description}</span></> : null}</p>
        <div className="row">
          <button className="btn small" type="button" id="land-highlight" onClick={() => onToggleTopic(topic.id)}>{slots.includes(topic.id) ? 'Remove topic highlight' : 'Highlight this topic'}</button>
          <button className="btn small primary" type="button" id="land-ask" onClick={() => askQuestion(`What does the collection report about ${topic.label.toLowerCase()}?`)}>Ask about “{topic.label}”</button>
        </div>
      </> : <p className="muted small">This item does not belong to a clear topic.</p>}
      <h4 style={{ marginTop: 20 }}>Related evidence <span className="muted small">(most similar passages)</span></h4>
      <ul className="plain">
        {related.map(r => (
          <li key={r.id} style={{ marginBottom: 10 }}>
            <button type="button" className="linklike" onClick={() => onSelect(r.id)}>Show on map</button> <LandItem p={r} /><br />
            <span className="small muted">{r.snippet.slice(0, 180)}{r.snippet.length > 180 ? '…' : ''}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
