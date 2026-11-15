import { describe, expect, it } from 'vitest';
import { createNdjsonParser } from './api';

describe('createNdjsonParser', () => {
  it('handles events split across chunks and skips bad lines', () => {
    const got: unknown[] = [];
    const p = createNdjsonParser(e => got.push(e));
    p.push('{"type":"progress","stage":"a"}\n{"type":"pro');
    p.push('gress","stage":"b"}\nnot json\n\n');
    p.push('{"type":"result","answer":null}');
    expect(got).toHaveLength(2);
    p.end();
    expect(got).toEqual([{ type: 'progress', stage: 'a' }, { type: 'progress', stage: 'b' }, { type: 'result', answer: null }]);
  });
  it('propagates errors thrown by the handler', () => {
    const p = createNdjsonParser(e => { if (e.type === 'error') throw new Error('boom'); });
    expect(() => p.push('{"type":"error"}\n')).toThrow('boom');
  });
});
