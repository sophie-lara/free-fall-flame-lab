import { milestones, stepIconKind, summaryLabel } from '../../lib/ask';
import { fmt } from '../../lib/format';
import type { ProgressEvent, Turn } from '../../lib/types';
import { RECOMMENDED } from '../../lib/recommended';
import { useApp } from '../../state/AppState';
import { AnswerView } from './AnswerView';

import { CheckIcon, StepIcon } from './icons';

function Step({ s, cls }: { s: ProgressEvent; cls: string }) {
  return <li className={cls}><span className="step-icon"><StepIcon kind={stepIconKind(s.stage)} /></span><span className="step-text">{s.message}</span><span className="muted small">{fmt(s.elapsed_s, 3)} s</span></li>;
}

/** The real steps as one line, ticked off as they finish, beside a morphing flame. */
function Progress({ steps, ai }: { steps: ProgressEvent[]; ai: boolean }) {
  const { items } = milestones(steps, ai);
  const current = items.find(m => m.state === 'current') ?? items[items.length - 1];
  const latest = steps.length ? steps[steps.length - 1] : null;
  return (
    <section className="card progress-card" aria-label="Progress">
      <div className="progress-row">
        <ol className="milestones">
          {items.map(m => (
            <li key={m.key} className={`ms ms-${m.state}`} aria-current={m.state === 'current' ? 'step' : undefined}>
              <span className="ms-mark" aria-hidden="true">{m.state === 'done' ? <CheckIcon /> : <span className="ms-dot" />}</span>
              <span className="ms-label">{m.label}</span>
            </li>
          ))}
        </ol>
        <span className="muted small progress-time">{latest ? `${fmt(latest.elapsed_s, 3)} s` : ''}</span>
      </div>
      {latest && <p className="progress-detail muted small">{latest.message}</p>}
      <p className="visually-hidden" aria-live="polite">{current.label}</p>
    </section>
  );
}

/** After the answer arrives, the steps stay as a collapsed summary above it. */
function StepsSummary({ steps, answered, failed = false }: { steps: ProgressEvent[]; answered: boolean; failed?: boolean }) {
  if (!steps?.length) return null;
  const label = summaryLabel(fmt(steps[steps.length - 1].elapsed_s, 3), answered, failed);
  return (
    <details className="card steps-summary">
      <summary>
        <span className="row" style={{ gap: 8 }}>{failed && '⚠'}<span>{label}</span></span>
        <span className="muted small">{steps.length} step{steps.length === 1 ? '' : 's'}</span>
      </summary>
      <ol className="steps fire-steps">{steps.map((s, i) => <Step key={i} s={s} cls="done" />)}</ol>
    </details>
  );
}

/** A friendly reply to a greeting or small talk, with a few questions to start from. */
function Reply({ text }: { text: string }) {
  const { sendQuestion, asking } = useApp();
  const starters = RECOMMENDED[0]?.questions.slice(0, 3) ?? [];
  return (
    <section className="card reply-card">
      <p style={{ margin: 0 }}>{text}</p>
      {starters.length > 0 && (
        <div className="chips" style={{ marginTop: 12 }} aria-label="Questions to start with">
          {starters.map(q => <button key={q} type="button" className="chip" disabled={asking} onClick={() => sendQuestion(q)}>{q}</button>)}
        </div>
      )}
    </section>
  );
}

function TurnBody({ t }: { t: Turn }) {
  if (t.loading) return <Progress steps={t.progress} ai={t.ai} />;
  if (t.error) return <><StepsSummary steps={t.progress} answered={false} failed /><div className="error" role="alert">{t.error}</div></>;
  if (!t.result) return null;
  if (t.result.reply) return <Reply text={t.result.reply} />;
  return <><StepsSummary steps={t.progress} answered={!!t.result.answer} /><AnswerView turn={t} /></>;
}

export function TurnView({ t }: { t: Turn }) {
  return (
    <article className="turn" id={`turn-${t.id}`}>
      <div className="msg user"><div className="bubble">{t.question}</div></div>
      <div className="msg bot"><img className="avatar" src="/logo.svg" alt="" width="28" height="28" /><div className="turn-body"><TurnBody t={t} /></div></div>
    </article>
  );
}
