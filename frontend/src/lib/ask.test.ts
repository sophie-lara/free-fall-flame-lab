import { describe, expect, it } from 'vitest';
import {
  askRequest, buildFootnotes, evidenceType, fireState, groupSupports, historyFor, limitsHint, similarQuotes, stepIconKind, stripLabel,
} from './ask';
import type { Turn } from './types';

const turn = (id: string, question: string, claims: string[] | null, error = ''): Turn => ({
  id, question, ai: true, loading: false, progress: [], error,
  result: claims ? { kind: 'answer', answer: { status: 'answered', claims: claims.map(text => ({ text, supports: [] })) } } : null,
});

describe('stripLabel', () => {
  it('removes evidence label prefixes', () => {
    expect(stripLabel('Document evidence: Flames spread slower.')).toBe('Flames spread slower.');
    expect(stripLabel('Structured table record evidence — 13.6 %')).toBe('13.6 %');
    expect(stripLabel('Figure description evidence - the duct')).toBe('the duct');
    expect(stripLabel('visual evidence:x')).toBe('x');
  });
  it('leaves ordinary text alone', () => {
    expect(stripLabel('Evidence shows that flames spread.')).toBe('Evidence shows that flames spread.');
  });
});

describe('similarQuotes and groupSupports', () => {
  it('detects near-duplicates by word overlap', () => {
    expect(similarQuotes('The flame spread rate decreased with lower oxygen', 'the flame spread rate decreased with lower oxygen levels')).toBe(true);
    expect(similarQuotes('The flame spread rate decreased', 'Smoke does not rise in orbit')).toBe(false);
    expect(similarQuotes('', 'anything')).toBe(false);
  });
  it('groups a claim\'s supports', () => {
    const groups = groupSupports([
      { chunk_id: 'a', quote: 'The flame spread rate decreased with lower oxygen' },
      { chunk_id: 'b', quote: 'Smoke does not rise in orbit at all' },
      { chunk_id: 'c', quote: 'the flame spread rate decreased with lower oxygen levels' },
    ]);
    expect(groups.map(g => g.map(s => s.chunk_id))).toEqual([['a', 'c'], ['b']]);
  });
});

describe('buildFootnotes', () => {
  it('numbers by first appearance and reuses a chunk\'s number', () => {
    const { claims, notes } = buildFootnotes([
      { text: 'Document evidence: First.', supports: [{ chunk_id: 'x', quote: 'alpha beta gamma delta' }, { chunk_id: 'y', quote: 'one two three four' }] },
      { text: 'Second.', supports: [{ chunk_id: 'z', quote: 'red green blue yellow' }, { chunk_id: 'x', quote: 'alpha beta gamma delta' }] },
    ]);
    expect(claims).toEqual([{ text: 'First.', markers: [1, 2] }, { text: 'Second.', markers: [3, 1] }]);
    expect(notes.map(n => [n.n, n.primary.chunk_id])).toEqual([[1, 'x'], [2, 'y'], [3, 'z']]);
  });
  it('folds near-duplicate quotes from other chunks into one footnote', () => {
    const { claims, notes } = buildFootnotes([
      { text: 'A.', supports: [{ chunk_id: 'p1', quote: 'The flame shrinks to a hemispherical blue shape just before quenching.' }] },
      { text: 'B.', supports: [{ chunk_id: 'p2', quote: 'the flame shrinks to a hemispherical blue shape just before quenching' }, { chunk_id: 'p3', quote: 'Smoke does not rise' }] },
    ]);
    expect(notes).toHaveLength(2);
    expect(notes[0].also.map(s => s.chunk_id)).toEqual(['p2']);
    expect(claims[1].markers).toEqual([1, 2]);
  });
  it('does not repeat a marker within one claim', () => {
    const { claims } = buildFootnotes([{ text: 'A.', supports: [{ chunk_id: 'k', quote: 'q one two' }, { chunk_id: 'k', quote: 'q one two' }] }]);
    expect(claims[0].markers).toEqual([1]);
  });
});

describe('historyFor', () => {
  it('keeps the last three answered turns, excluding errors and the current turn', () => {
    const turns = [turn('1', 'q1', ['a1']), turn('2', 'q2', null, 'boom'), turn('3', 'q3', ['a3', 'b3']), turn('4', 'q4', ['a4']), turn('5', 'q5', ['a5']), turn('6', 'q6', null)];
    expect(historyFor(turns, '6')).toEqual([
      { question: 'q3', answer: 'a3 b3' }, { question: 'q4', answer: 'a4' }, { question: 'q5', answer: 'a5' },
    ]);
  });
  it('truncates long questions and answers', () => {
    const h = historyFor([turn('1', 'x'.repeat(1500), ['y'.repeat(5000)])]);
    expect(h[0].question).toHaveLength(1000);
    expect(h[0].answer).toHaveLength(4000);
  });
  it('treats keyword-only results as answered with an empty answer', () => {
    const t: Turn = { ...turn('1', 'q', null), result: { kind: 'answer', results: [] } };
    expect(historyFor([t])).toEqual([{ question: 'q', answer: '' }]);
  });
});

describe('askRequest', () => {
  it('AI on uses hybrid retrieval and provider calls', () => {
    expect(askRequest('q', true, [], ['s'])).toEqual({ question: 'q', history: [], method: 'hybrid', generate_answer: true, allow_provider_calls: true, include_sources: ['s'] });
  });
  it('AI off is keyword only with no provider calls', () => {
    expect(askRequest('q', false, [], [])).toEqual({ question: 'q', history: [], method: 'keyword', generate_answer: false, allow_provider_calls: false, include_sources: [] });
  });
});

describe('limitsHint', () => {
  it('is empty when limits are off or exempt', () => {
    expect(limitsHint(null)).toBe('');
    expect(limitsHint({ enabled: false })).toBe('');
    expect(limitsHint({ enabled: true, exempt: true, remaining_today: 0 })).toBe('');
  });
  it('describes what is left', () => {
    expect(limitsHint({ enabled: true, remaining_today: 0 })).toBe(' AI answers for today are used up; keyword search still works.');
    expect(limitsHint({ enabled: true, remaining_today: 1 })).toBe(' 1 AI answer left today (site-wide).');
    expect(limitsHint({ enabled: true, remaining_today: 5, next_available_in_s: 30 })).toBe(' 5 AI answers left today (site-wide). Next one available in 30 s.');
  });
});

describe('progress fire', () => {
  it('maps stages to icons', () => {
    expect(stepIconKind('keyword')).toBe('log');
    expect(stepIconKind('generating')).toBe('flame');
    expect(stepIconKind('checking')).toBe('check');
    expect(stepIconKind('started')).toBe('dot');
  });
  it('titles the card by progress', () => {
    expect(fireState([]).title).toBe('Striking a match…');
    expect(fireState([{ stage: 'keyword', message: '', elapsed_s: 0 }]).title).toBe('Adding logs to the fire…');
    expect(fireState([{ stage: 'keyword', message: '', elapsed_s: 0 }, { stage: 'generating', message: '', elapsed_s: 1 }])).toEqual({ logs: 1, lit: true, title: 'Burning…' });
  });
  it('classifies evidence', () => {
    expect(evidenceType({ chunk_id: 'a', source_id: 's', filename: 'f', record_card: { kind: 'row' } })).toBe('table');
    expect(evidenceType({ chunk_id: 'a', source_id: 's', filename: 'f', visual: { kind: 'Figure', label: '1' } })).toBe('figure');
    expect(evidenceType(undefined)).toBe('report');
  });
});
