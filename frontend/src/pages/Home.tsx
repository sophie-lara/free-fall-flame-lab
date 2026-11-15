import { useRef } from 'react';
import { FlameStory, HERO_CREDIT, HeroFlames } from '../components/FlameStory';
import { useApp } from '../state/AppState';
import { count, scrollBehavior } from '../lib/format';

export const HOME_TRY = [
  'How does opposed-flow velocity affect flame spread over thin PMMA?',
  'What was the initial CO reading for BASS-II test O12?',
  'Which components are labelled in Figure 5.1 of the BASS-II duct schematic?',
  'What did the Saffire experiments show about flame spread on large samples?',
];

function Tile({ href, icon, title, text }: { href: string; icon: string; title: string; text: string }) {
  return <a className="card tile" href={href}><span className="tile-icon" aria-hidden="true">{icon}</span><h3>{title}</h3><p>{text}</p><span className="go">Open →</span></a>;
}
function Stat({ value, label }: { value: string; label: string }) {
  return <div className="card stat"><div className="value">{value}</div><div className="label">{label}</div></div>;
}

export function Home() {
  const { me, corpus, coverage, askQuestion } = useApp();
  const storyRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const t = corpus?.totals || {};
  const runs = coverage?.records?.length;
  return (
    <>
      <section className="hero">
        <div>
          <h1>Decades of NASA microgravity-combustion research, at your fingertips.</h1>
          <p className="lead">Combustion Atlas makes NASA's spacecraft fire-safety experiments searchable and comparable: every answer quotes the original report and page, and the coverage map shows where the evidence is thin.</p>
          <form className="hero-search" id="hero-search" role="search" onSubmit={e => {
            e.preventDefault();
            const q = inputRef.current?.value.trim();
            if (q) askQuestion(q);
          }}>
            <label htmlFor="hero-q" className="visually-hidden" hidden>Question</label>
            <input id="hero-q" ref={inputRef} type="search" maxLength={1000} placeholder="e.g. How does opposed-flow velocity affect flame spread?" aria-label="Ask a question" />
            <button className="btn primary" type="submit">Ask</button>
          </form>
          <div className="chips hero-try" aria-label="Try asking"><span className="hint" style={{ margin: 0 }}>Try:</span>
            {HOME_TRY.map(q => <button key={q} type="button" className="chip" onClick={() => askQuestion(q)}>{q}</button>)}
          </div>
        </div>
        <div className="fs-hero-wrap">
          <button type="button" className="fs-hero" id="fs-hero" aria-label="Why fire is different in space: open the story"
            onClick={() => storyRef.current?.scrollIntoView({ behavior: scrollBehavior(), block: 'start' })}>
            <HeroFlames /><span className="fs-hero-cta">Why fire is different in space ↓</span>
          </button>
          <p className="fs-hero-credit">{HERO_CREDIT}</p>
        </div>
      </section>
      <section className="section fs-section" id="fire-story" aria-labelledby="fs-title" ref={storyRef}>
        <FlameStory onAsk={askQuestion} />
      </section>
      <section className="section">
        <div className={`grid cols-${me?.can_upload ? 4 : 3}`}>
          <Tile href="#/ask" icon="?" title="Ask a question" text="Get answers built only from indexed NASA documents, with every claim linked to its page. Ask follow-ups in a chat." />
          <Tile href="#/coverage" icon="◎" title="Experiment coverage" text="See which conditions have been tested across investigations, and where this collection has no runs." />
          <Tile href="#/landscape" icon="⁘" title="Evidence landscape" text="A map of every indexed passage, figure and table, grouped into topics, with related evidence one click away." />
          {me?.can_upload ? <Tile href="#/upload" icon="+" title="Add to corpus" text={me.is_admin ? 'Upload a NASA report or paper (PDF) and review visitor uploads.' : 'Upload a PDF and ask questions about it. It stays private until reviewed.'} /> : null}
        </div>
      </section>
      <section className="section">
        <div className="section-head"><h2>Data sources</h2><a href="#/sources">View all sources →</a></div>
        <div className="grid cols-5">
          <Stat value={count(t.documents)} label="Documents" />
          <Stat value={count(t.investigations)} label="Investigations" />
          <Stat value={count(t.pages)} label="Pages indexed" />
          <Stat value={count(t.figures)} label="Figures described" />
          <Stat value={runs == null ? '—' : count(runs)} label="Experiment runs" />
        </div>
        <p className="hint">Documents come from NASA's Physical Sciences Informatics repository and technical reports. Experiment runs come from NASA PSI experiment tables.</p>
      </section>
    </>
  );
}
