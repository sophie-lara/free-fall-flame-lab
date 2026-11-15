// Explore → Evidence landscape.
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { EmptyBox, LegendShape, PageHead } from '../../components/common';
import { useApp } from '../../state/AppState';
import { count, scrollBehavior } from '../../lib/format';
import { initialSlots, toggleSlot } from '../../lib/landscape';
import { LandDetail } from './LandDetail';
import { LandMap2D } from './LandMap2D';
import { Land3D } from './Land3D';
import { TopicMenu } from './TopicMenu';
import { TopicTable } from './TopicTable';

const LEAD = 'Every indexed passage, figure description and reviewed table, placed so that passages with similar meaning sit close together. Topics are found automatically. Use it to see what the collection covers and to jump between related evidence.';

export function LandscapePage() {
  const { landscape: d, landscapeError, loadLandscape, land: L, setLand } = useApp();
  const location = useLocation();
  const detailRef = useRef<HTMLDivElement>(null);
  const dimRef = useRef<HTMLButtonElement>(null);
  const focusDim = useRef(false);

  useEffect(() => { if (!d && !landscapeError) loadLandscape(); }, [d, landscapeError, loadLandscape]);

  // Start with the three largest topics highlighted; #/landscape?view=3d opens the 3-D view.
  useEffect(() => {
    if (!d || L.initialized) return;
    setLand({ slots: initialSlots(d.clusters), initialized: true, ...(/[?&]view=3d\b/.test(location.search) ? { view: 'three' as const } : {}) });
  }, [d, L.initialized, location.search, setLand]);

  const lastNonce = useRef(L.selectNonce);
  useEffect(() => {
    if (L.selectNonce === lastNonce.current) return;
    lastNonce.current = L.selectNonce;
    detailRef.current?.scrollIntoView({ behavior: scrollBehavior(), block: 'nearest' });
  }, [L.selectNonce]);

  useEffect(() => {
    if (focusDim.current) { focusDim.current = false; dimRef.current?.focus(); }
  }, [L.view]);

  const head = <PageHead eyebrow="Explore" title={<span id="land-title">Evidence landscape</span>} lead={LEAD} />;
  if (landscapeError) return <section id="explore-land" aria-labelledby="land-title">{head}<EmptyBox title="Not available yet" text={landscapeError} /></section>;
  if (!d || !L.initialized) return <section id="explore-land" aria-labelledby="land-title">{head}<p className="loading">Loading the evidence landscape…</p></section>;

  const topicName = (id: number) => d.byCluster[id]?.label || 'No topic';
  const toggleTopic = (id: number) => setLand(l => {
    const r = toggleSlot(l.slots, id);
    return r.added ? { slots: r.slots, flyTo: id } : { slots: r.slots };
  });
  const select = (id: string | null) => setLand(l => ({ selected: id, selectNonce: id ? l.selectNonce + 1 : l.selectNonce }));
  const toggleDim = () => { focusDim.current = true; setLand(l => ({ view: l.view === 'three' ? 'chart' : 'three' })); };
  const active = L.slots.some(s => s !== null);
  const legendTopics = L.slots.map((id, i) => (id !== null ? <span key={i}><LegendShape shape="circle" color={`var(--s${i + 1})`} />{topicName(id)}</span> : null));

  return (
    <section id="explore-land" aria-labelledby="land-title">
      {head}
      <div className="row" style={{ marginBottom: 16 }}>
        {d.stale ? <span className="pill warn">Documents changed since this map was built; new ones are not shown yet</span> : null}
        <span className="muted small">{count(d.points.length)} items · {count(d.clusters.length)} topics · {count(d.noise)} without a clear topic</span>
      </div>
      <section className="card">
        <div className="controls">
          <TopicMenu clusters={d.clusters} slots={L.slots} open={L.menuOpen} onOpenChange={open => setLand({ menuOpen: open })}
            onToggle={toggleTopic} onClear={() => setLand({ slots: [null, null, null] })} />
          <div className="legend land-selected" aria-label="Highlighted topics">{legendTopics}</div>
          <span className="spacer" />
          <button type="button" className="btn small" aria-pressed={L.view === 'table'} onClick={() => setLand(l => (
            l.view === 'table' ? { view: l.lastMap } : { lastMap: l.view === 'three' ? 'three' : 'chart', view: 'table' }
          ))}>{L.view === 'table' ? 'Show map' : 'Topic list'}</button>
        </div>
        <div id="land-view" style={{ marginTop: 16 }}>
          {L.view === 'table' ? <TopicTable clusters={d.clusters} slots={L.slots} onToggle={toggleTopic} />
            : L.view === 'three' ? <Land3D data={d} slots={L.slots} selected={L.selected} onSelect={select} legendTopics={legendTopics} active={active} dimRef={dimRef} onToggleDim={toggleDim} topicName={topicName} />
            : <LandMap2D data={d} slots={L.slots} selected={L.selected} onSelect={select} legendTopics={legendTopics} active={active} dimRef={dimRef} onToggleDim={toggleDim} topicName={topicName} />}
        </div>
      </section>
      <div id="land-detail" className="section" aria-live="polite" ref={detailRef}>
        <LandDetail data={d} selected={L.selected} slots={L.slots} onClose={() => select(null)} onToggleTopic={toggleTopic} onSelect={select} />
      </div>
      <details className="section small muted"><summary>How this map is made</summary>
        <ul className="plain">
          {(d.notes || []).map((n, i) => <li key={i}>{n}</li>)}
          <li>Method: {d.params?.projection}; {d.params?.clustering}; related evidence by {d.params?.neighbors}. Nearby points have similar meaning.</li>
          {d.generated_at ? <li>Built {d.generated_at.slice(0, 10)}.</li> : null}
        </ul>
      </details>
    </section>
  );
}
