// Pure logic behind the Ask chat: request bodies, follow-up history, claim text and footnotes.
import type { AskRequest, Claim, HistoryItem, Limits, ProgressEvent, SearchResult, Support, Turn } from './types';

/** Earlier answered turns, compacted, so follow-ups ("what about FLEX?") can be understood. */
export function historyFor(turns: Turn[], exclude?: Turn | string): HistoryItem[] {
  const excludeId = typeof exclude === 'string' ? exclude : exclude?.id;
  return turns
    .filter(t => t.id !== excludeId && t.result && !t.error)
    .slice(-3)
    .map(t => ({
      question: t.question.slice(0, 1000),
      answer: (t.result?.answer?.claims || []).map(c => c.text).join(' ').slice(0, 4000),
    }));
}

/** AI off: keyword search only, no provider calls of any kind. */
export function askRequest(question: string, ai: boolean, history: HistoryItem[], include_sources: string[]): AskRequest {
  return ai
    ? { question, history, method: 'hybrid', generate_answer: true, allow_provider_calls: true, include_sources }
    : { question, history, method: 'keyword', generate_answer: false, allow_provider_calls: false, include_sources };
}

export function limitsHint(l: Limits | null): string {
  if (!l || !l.enabled || l.exempt) return '';
  if (l.remaining_today === 0) return ' AI answers for today are used up; keyword search still works.';
  const left = l.remaining_today != null ? ` ${l.remaining_today} AI answer${l.remaining_today === 1 ? '' : 's'} left today (site-wide).` : '';
  const wait = l.next_available_in_s ? ` Next one available in ${l.next_available_in_s} s.` : '';
  return left + wait;
}

// ---------- progress as a fire ----------
export const FUEL_STAGES = new Set(['keyword', 'embedding', 'semantic', 'ranking', 'records', 'figures', 'retrieved', 'context']);
const FLAME_STAGES = ['generating', 'retrying', 'fallback', 'answer'];
const CHECK_STAGES = ['checking', 'repairing', 'filtering'];
export type StepIconKind = 'log' | 'flame' | 'check' | 'dot';

export function stepIconKind(stage: string): StepIconKind {
  if (FUEL_STAGES.has(stage)) return 'log'; // search adds fuel
  if (FLAME_STAGES.includes(stage)) return 'flame'; // writing burns it
  if (CHECK_STAGES.includes(stage)) return 'check'; // fact checks
  return 'dot';
}

export function fireState(steps: ProgressEvent[]): { logs: number; lit: boolean; title: string } {
  const logs = steps.filter(s => FUEL_STAGES.has(s.stage)).length;
  const lit = steps.some(s => FLAME_STAGES.includes(s.stage));
  const title = lit ? 'Burning…' : logs ? 'Adding logs to the fire…' : 'Striking a match…';
  return { logs, lit, title };
}

// ---------- claim text and quotes ----------
export const LABEL_PREFIX = /^\s*(?:structured\s+)?(?:document|table(?:\s+record)?|record|figure|visual)(?:\s+description)?\s+evidence\s*[:\-–—]\s*/i;
export const stripLabel = (text: unknown): string => String(text).replace(LABEL_PREFIX, '');

export function quoteTokens(text: unknown): Set<string> {
  return new Set(String(text).toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(w => w.length > 2));
}

/** Two quotes are near-duplicates when their word sets overlap by at least 60 % (Jaccard). */
export function similarQuotes(a: unknown, b: unknown): boolean {
  const x = quoteTokens(a), y = quoteTokens(b);
  if (!x.size || !y.size) return false;
  let shared = 0;
  x.forEach(w => { if (y.has(w)) shared += 1; });
  return shared / (x.size + y.size - shared) >= 0.6;
}

/** Groups a claim's supports so near-duplicate quotes appear once ("Also stated in"). */
export function groupSupports(supports: Support[]): Support[][] {
  const groups: Support[][] = [];
  supports.forEach(s => {
    const group = groups.find(g => similarQuotes(g[0].quote, s.quote));
    if (group) group.push(s); else groups.push([s]);
  });
  return groups;
}

// ---------- footnotes ----------
export interface Footnote {
  n: number;
  /** The first support given this number; its quote is shown. */
  primary: Support;
  /** Near-duplicate quotes from other chunks, listed as extra sources. */
  also: Support[];
}
export interface FootnotedClaim { text: string; markers: number[] }
export interface FootnotedAnswer { claims: FootnotedClaim[]; notes: Footnote[] }

/**
 * Numbers sources by first appearance across the whole answer. A chunk cited twice keeps its
 * number; a near-duplicate quote from another chunk joins the existing footnote.
 */
export function buildFootnotes(claims: Claim[]): FootnotedAnswer {
  const notes: Footnote[] = [];
  const byChunk = new Map<string, Footnote>();
  const out = claims.map(claim => {
    const markers: number[] = [];
    for (const s of claim.supports || []) {
      let note = byChunk.get(s.chunk_id);
      if (!note) {
        note = notes.find(f => similarQuotes(f.primary.quote, s.quote));
        if (note) note.also.push(s);
        else { note = { n: notes.length + 1, primary: s, also: [] }; notes.push(note); }
        byChunk.set(s.chunk_id, note);
      }
      if (!markers.includes(note.n)) markers.push(note.n);
    }
    return { text: stripLabel(claim.text), markers };
  });
  return { claims: out, notes };
}

export type EvidenceType = 'table' | 'figure' | 'report';
export function evidenceType(src: SearchResult | undefined): EvidenceType {
  if (src?.record_card || src?.record_row) return 'table';
  if (src?.visual) return 'figure';
  return 'report';
}

export const isTableHit = (r: SearchResult): boolean =>
  !!r.record_card && (r.record_card.kind === 'row' || r.record_card.kind === 'table');

export const isVisualCrop = (r: SearchResult | undefined): boolean =>
  !!r?.visual && String(r.crop_url || '').startsWith('/api/visuals/');
