import type { CSSProperties } from 'react';
import { fireState, stepIconKind } from '../../lib/ask';
import { fmt } from '../../lib/format';
import type { ProgressEvent, Turn } from '../../lib/types';
import { AnswerView } from './AnswerView';
import { DotIcon, LogIcon, StepIcon } from './icons';

function Step({ s, cls }: { s: ProgressEvent; cls: string }) {
  return <li className={cls}><span className="step-icon"><StepIcon kind={stepIconKind(s.stage)} /></span><span className="step-text">{s.message}</span><span className="muted small">{fmt(s.elapsed_s, 3)} s</span></li>;
}

/** Progress as a fire: search steps add logs, writing the answer ignites it. */
function Progress({ steps }: { steps: ProgressEvent[] }) {
  const { logs, lit, title } = fireState(steps);
  const fuel = Math.min(logs, 6);
  return (
    <section className="card burn-card" aria-label="Progress">
      <div className="row">
        <span className={`burn-flame${lit ? ' lit' : ''}`} style={{ ['--fuel' as string]: fuel } as CSSProperties} aria-hidden="true"><img src="/logo.svg" alt="" width="28" height="28" /></span>
        <h3 style={{ margin: 0 }} aria-live="polite">{title}</h3>
        <span className="burn-logs" aria-label={`${logs} search steps`}>{Array.from({ length: fuel }, (_, i) => <LogIcon key={i} />)}</span>
        <span className="spacer" />
        <span className="muted small">{steps.length ? `${fmt(steps[steps.length - 1].elapsed_s, 3)} s` : ''}</span>
      </div>
      <ol className="steps fire-steps">
        {steps.length
          ? steps.map((s, i) => <Step key={i} s={s} cls={i === steps.length - 1 ? 'current' : 'done'} />)
          : <li className="current"><span className="step-icon"><DotIcon /></span><span className="step-text">Starting…</span></li>}
      </ol>
    </section>
  );
}

/** After the answer arrives, the steps stay as a collapsed summary above it. */
function StepsSummary({ steps, failed = false }: { steps: ProgressEvent[]; failed?: boolean }) {
  if (!steps?.length) return null;
  const total = fmt(steps[steps.length - 1].elapsed_s, 3);
  const label = failed ? `Fizzled out after ${total} s` : `Burned in ${total} s`;
  return (
    <details className="card steps-summary">
      <summary>
        <span className="row" style={{ gap: 8 }}>{failed ? '⚠' : <img src="/logo.svg" alt="" width="18" height="18" className="burn-done" />}<span>{label}</span></span>
        <span className="muted small">{steps.length} step{steps.length === 1 ? '' : 's'}</span>
      </summary>
      <ol className="steps fire-steps">{steps.map((s, i) => <Step key={i} s={s} cls="done" />)}</ol>
    </details>
  );
}

function TurnBody({ t }: { t: Turn }) {
  if (t.loading) return <Progress steps={t.progress} />;
  if (t.error) return <><StepsSummary steps={t.progress} failed /><div className="error" role="alert">{t.error}</div></>;
  if (!t.result) return null;
  return <><StepsSummary steps={t.progress} /><AnswerView turn={t} /></>;
}

export function TurnView({ t }: { t: Turn }) {
  return (
    <article className="turn" id={`turn-${t.id}`}>
      <div className="msg user"><div className="bubble">{t.question}</div></div>
      <div className="msg bot"><img className="avatar" src="/logo.svg" alt="" width="28" height="28" /><div className="turn-body"><TurnBody t={t} /></div></div>
    </article>
  );
}
