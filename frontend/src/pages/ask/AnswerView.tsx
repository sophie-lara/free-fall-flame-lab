// An answer as continuous prose with numbered footnotes for its sources.
import { Fragment, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { buildFootnotes, evidenceType, isVisualCrop } from '../../lib/ask';
import type { Footnote } from '../../lib/ask';
import { docLink, scrollBehavior } from '../../lib/format';
import type { AskResult, SearchResult, Support, Turn } from '../../lib/types';
import { SourcesSummary } from './SourcesSummary';
import { EvidencePill } from './TableData';

type ById = Record<string, SearchResult>;

/** Plain-text name of a support's source, for tooltips. */
function sourceText(s: Support, byId: ById): string {
  const src = byId[s.chunk_id];
  if (src?.record_card) return src.record_card.locator || src.filename || 'Reviewed evidence';
  if (src?.source_id) return `${src.filename || 'Source'}, page ${src.physical_page}`;
  return s.chunk_id;
}

function SourceLink({ s, byId }: { s: Support; byId: ById }) {
  const src = byId[s.chunk_id];
  if (src?.record_card) return <>{src.record_card.locator || src.filename || 'Reviewed evidence'}</>;
  if (src?.source_id) return <a href={docLink(src.source_id, src.physical_page)} target="_blank" rel="noopener noreferrer">{src.filename || 'Source'}, page {src.physical_page} ↗</a>;
  return <>{s.chunk_id}</>;
}

function EvidenceBadge({ src }: { src?: SearchResult }) {
  const type = evidenceType(src);
  if (type === 'table') return <span className="pill ok">Reviewed table</span>;
  if (type === 'figure') return <span className="pill warn">AI figure description</span>;
  return <span className="pill">Report</span>;
}

/** Where a footnote's quote comes from: a page link, or a reviewed table record. */
function FootnoteSource({ s, byId }: { s: Support; byId: ById }) {
  const src = byId[s.chunk_id];
  const card = src?.record_card;
  if (card) {
    const open = Array.isArray(card.open_questions) ? card.open_questions.length : Number(card.open_questions || 0);
    const what = card.kind === 'row' ? `Table row ${card.test_id}` : card.kind === 'table' ? `Table · ${card.table_title}` : 'Table record';
    return (
      <>
        <span className="pill ok">{what}</span>{card.evidence_kind ? <> <EvidencePill kind={card.evidence_kind} /></> : null}
        {' '}<span>{card.locator || src.filename || 'Reviewed evidence'}</span>
        {open ? <> · <span className="pill warn">{open} open question{open === 1 ? '' : 's'}</span></> : null}
      </>
    );
  }
  return (
    <>
      <SourceLink s={s} byId={byId} />
      {src?.visual ? <span className="muted"> · {src.visual.kind} {src.visual.label}</span> : null}
    </>
  );
}

const truncate = (text: string, n: number) => (text.length > n ? `${text.slice(0, n).trimEnd()}…` : text);

function Marker({ n, turnId, first, tipId, note, byId, onJump }: {
  n: number; turnId: string; first: boolean; tipId: string; note: Footnote; byId: ById; onJump: (n: number) => void;
}) {
  const [dismissed, setDismissed] = useState(false);
  return (
    <sup className={`fn-ref${dismissed ? ' dismissed' : ''}`} onMouseLeave={() => setDismissed(false)}>
      <a
        id={first ? `fnref-${turnId}-${n}` : undefined}
        href={`#fn-${turnId}-${n}`}
        aria-label={`Source ${n}`}
        aria-describedby={tipId}
        onClick={e => { e.preventDefault(); onJump(n); }}
        onKeyDown={e => { if (e.key === 'Escape') setDismissed(true); }}
        onBlur={() => setDismissed(false)}
      >{n}</a>
      <span className="fn-tip" role="tooltip" id={tipId}>
        <span className="fn-tip-quote">“{truncate(note.primary.quote, 220)}”</span>
        <span className="fn-tip-src">{sourceText(note.primary, byId)}</span>
      </span>
    </sup>
  );
}

function AnswerCard({ turn, result, byId }: { turn: Turn; result: AskResult; byId: ById }) {
  const ans = result.answer!;
  const [flash, setFlash] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const answered = ans.status === 'answered';
  const partial = answered && (ans.limitations || []).length > 0;
  const status = !answered
    ? <span className="pill bad">Insufficient evidence</span>
    : partial ? <span className="pill warn">Partial evidence</span> : <span className="pill ok">Answered from sources</span>;
  const { claims, notes } = buildFootnotes(answered ? ans.claims : []);
  const byN = new Map(notes.map(f => [f.n, f]));
  const tid = turn.id;

  const jumpTo = (n: number) => {
    const el = document.getElementById(`fn-${tid}-${n}`);
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: scrollBehavior() });
    el.focus({ preventScroll: true });
    setFlash(n);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setFlash(null), 1600);
  };
  const backTo = (n: number) => {
    const el = document.getElementById(`fnref-${tid}-${n}`);
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: scrollBehavior() });
    el.focus({ preventScroll: true });
  };

  const seen = new Set<number>();
  const prose: ReactNode[] = claims.map((c, i) => (
    <Fragment key={i}>
      {i ? ' ' : ''}{c.text}
      {c.markers.map(n => {
        const first = !seen.has(n); seen.add(n);
        return <Marker key={n} n={n} turnId={tid} first={first} tipId={`fntip-${tid}-${i}-${n}`} note={byN.get(n)!} byId={byId} onJump={jumpTo} />;
      })}
    </Fragment>
  ));

  return (
    <section className="card stack">
      <div className="row"><h2 style={{ margin: 0 }}>Answer</h2>{status}</div>
      {answered ? <p className="answer-prose">{prose}</p> : <p>The indexed documents do not contain an answer to this question.</p>}
      {(ans.limitations || []).map((l, i) => <p key={i} className="notice">{l}</p>)}
      {notes.length ? (
        <div className="footnotes">
          <h3 className="footnotes-title" id={`fn-title-${tid}`}>Sources</h3>
          <ol className="footnote-list" aria-labelledby={`fn-title-${tid}`}>
            {notes.map(f => {
              const src = byId[f.primary.chunk_id];
              return (
                <li key={f.n} id={`fn-${tid}-${f.n}`} tabIndex={-1} className={`footnote${flash === f.n ? ' flash' : ''}`}>
                  <span className="fn-num" aria-hidden="true">{f.n}.</span>
                  <div className="fn-body">
                    <span className="visually-hidden">Source {f.n}: </span>
                    <q className="fn-quote">{f.primary.quote}</q>
                    <div className="cite fn-cite">
                      <EvidenceBadge src={src} /> <FootnoteSource s={f.primary} byId={byId} />
                      {' '}<a href={`#fnref-${tid}-${f.n}`} className="fn-back" aria-label={`Back to reference ${f.n} in the answer`} onClick={e => { e.preventDefault(); backTo(f.n); }}>↩</a>
                    </div>
                    {f.also.length ? <div className="cite also">Also stated in: {f.also.map((s, k) => <Fragment key={k}>{k ? ' · ' : ''}<SourceLink s={s} byId={byId} /></Fragment>)}</div> : null}
                    {isVisualCrop(src) ? (
                      <details><summary className="cite">View original page image</summary>
                        <img className="crop" loading="lazy" src={String(src.crop_url)} alt={`Original page for ${src.visual!.kind} ${src.visual!.label}`} /></details>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
    </section>
  );
}

/** Notices, the answer (or search results when AI is off) and the sources searched. */
export function AnswerView({ turn }: { turn: Turn }) {
  const result = turn.result!;
  const results = result.results || [];
  const byId: ById = Object.fromEntries(results.map(r => [r.chunk_id, r]));
  const ans = result.answer;
  const notices: ReactNode[] = [];
  if (result.limited) notices.push(<><strong>AI answers are paused.</strong> {result.limited.reason} Showing keyword search results below.</>);
  if (result.answer_unavailable) notices.push(<><strong>No AI answer this time.</strong> {result.answer_unavailable}</>);
  if (result.retrieval_fallback) notices.push(<>{result.retrieval_fallback}</>);
  if (result.answered_by?.backup) notices.push(<>Answered by the backup model {result.answered_by.model} ({result.answered_by.provider}) because the main model was unavailable. The same quote and number checks applied.</>);
  if (!ans && !result.limited && !result.answer_unavailable) notices.push(<><strong>AI answers are off.</strong> Showing keyword search results: reviewed table data first, then document passages.</>);
  const noticeCard = notices.length
    ? <section className="card notice" role="status">{notices.map((n, i) => <Fragment key={i}>{i ? <br /> : null}{n}</Fragment>)}</section>
    : null;
  if (!ans) return <>{noticeCard}<SourcesSummary results={results} /></>;
  return <>{noticeCard}<AnswerCard turn={turn} result={result} byId={byId} /><SourcesSummary results={results} fold /></>;
}
