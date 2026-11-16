import { useEffect, useLayoutEffect, useRef } from 'react';
import { RECOMMENDED } from '../../lib/recommended';
import { useApp } from '../../state/AppState';
import { UiSwitch } from '../../components/common';
import { limitsHint } from '../../lib/ask';
import { scrollBehavior } from '../../lib/format';
import { SendIcon } from './icons';
import { TurnView } from './TurnView';

// Recommended questions, grouped by what they demonstrate. Each was checked against the
// indexed corpus.

function Recommended({ onPick }: { onPick: (q: string) => void }) {
  return (
    <details className="recommended" open><summary>Recommended questions</summary>
      <div className="recommended-groups">
        {RECOMMENDED.map(g => (
          <div className="recommended-group" key={g.group}>
            <div className="recommended-title">{g.group}</div>
            <div className="hint" style={{ margin: '2px 0 8px' }}>{g.hint}</div>
            <div className="chips">{g.questions.map(q => <button key={q} type="button" className="chip" onClick={() => onPick(q)}>{q}</button>)}</div>
          </div>
        ))}
      </div>
    </details>
  );
}

export function Ask() {
  const { turns, asking, draft, setDraft, ai, toggleAi, newChat, sendQuestion, scrollReq, limits } = useApp();
  const qRef = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  // The composer grows with its text, up to 200 px.
  useLayoutEffect(() => {
    const q = qRef.current; if (!q) return;
    q.style.height = 'auto';
    q.style.height = `${Math.min(q.scrollHeight, 200)}px`;
  }, [draft]);

  // Scroll to a turn when it starts and when its answer arrives.
  const lastNonce = useRef(scrollReq?.nonce ?? 0);
  useEffect(() => {
    if (!scrollReq || scrollReq.nonce === lastNonce.current) return;
    lastNonce.current = scrollReq.nonce;
    document.getElementById(`turn-${scrollReq.id}`)?.scrollIntoView({ block: 'start', behavior: scrollBehavior() });
    if (scrollReq.focus) qRef.current?.focus({ preventScroll: true });
  }, [scrollReq]);

  const placeholder = turns.length ? 'Ask a follow-up or a new question…' : 'Ask about materials, conditions, results or methods…';
  return (
    <div className="chat">
      <div className="chat-head"><div><div className="eyebrow">Ask</div><h1>Ask the evidence</h1></div><span className="spacer" />
        {turns.length ? <button type="button" className="btn small" id="new-chat" onClick={() => { if (asking) return; newChat(); qRef.current?.focus(); }}>New chat</button> : null}
      </div>
      <div className="chat-thread" id="chat-thread" aria-live="polite">
        {turns.length ? turns.map(t => <TurnView key={t.id} t={t} />) : (
<Recommended onPick={sendQuestion} />
        )}
      </div>
      <form className="chat-composer" id="ask-form" ref={formRef} onSubmit={e => { e.preventDefault(); const text = draft.trim(); if (text) sendQuestion(text); }}>
        <div className="composer-box"><label htmlFor="q" className="visually-hidden">Question</label>
          <textarea id="q" ref={qRef} rows={1} maxLength={1000} placeholder={placeholder} value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); formRef.current?.requestSubmit(); } }} />
          <button className="send" type="submit" aria-label="Send" disabled={asking}><SendIcon /></button>
        </div>
        <div className="composer-meta">
          <UiSwitch id="ai-toggle" on={ai} label="AI answers" text={`AI ${ai ? 'on' : 'off'}`} onToggle={toggleAi} />
          <span className="hint" style={{ margin: 0 }}>{ai ? `Cited answers from the indexed documents.${limitsHint(limits)}` : 'Keyword search only: no AI calls.'}</span>
        </div>
      </form>
    </div>
  );
}
