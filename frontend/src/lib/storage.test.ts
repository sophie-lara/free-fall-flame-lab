import { beforeEach, describe, expect, it } from 'vitest';
import { loadChat, myUploads, rememberUpload, saveChat } from './storage';
import type { Turn } from './types';

class MemoryStorage {
  private m = new Map<string, string>();
  getItem(k: string) { return this.m.has(k) ? this.m.get(k)! : null; }
  setItem(k: string, v: string) { this.m.set(k, String(v)); }
  removeItem(k: string) { this.m.delete(k); }
  clear() { this.m.clear(); }
}
const g = globalThis as unknown as { localStorage: MemoryStorage; sessionStorage: MemoryStorage };

beforeEach(() => { g.localStorage = new MemoryStorage(); g.sessionStorage = new MemoryStorage(); });

describe('storage', () => {
  it('keeps the last 12 finished turns in sessionStorage', () => {
    const turns: Turn[] = Array.from({ length: 14 }, (_, i) => ({ id: String(i), question: `q${i}`, ai: false, loading: i === 13, progress: [], result: null, error: '' }));
    saveChat(turns);
    const saved = loadChat();
    expect(saved).toHaveLength(12);
    expect(saved[0].id).toBe('1');
    expect(JSON.parse(g.sessionStorage.getItem('atlas-chat')!)[0]).toEqual({ id: '1', question: 'q1', ai: false, loading: false, progress: [], result: null, error: '' });
  });
  it('survives bad JSON', () => {
    g.sessionStorage.setItem('atlas-chat', '{bad');
    expect(loadChat()).toEqual([]);
  });
  it('remembers up to 10 uploads without duplicates', () => {
    for (let i = 0; i < 12; i++) rememberUpload(`s${i}`, `f${i}.pdf`);
    rememberUpload('s5', 'again.pdf');
    const list = myUploads();
    expect(list).toHaveLength(10);
    expect(list.at(-1)).toEqual({ source_id: 's5', filename: 'again.pdf' });
    expect(list.filter(u => u.source_id === 's5')).toHaveLength(1);
  });
});
