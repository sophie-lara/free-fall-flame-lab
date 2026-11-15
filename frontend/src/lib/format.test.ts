import { describe, expect, it } from 'vitest';
import { count, docLink, fmt, invName, prettyField, psiLink, safeURL } from './format';

describe('format helpers', () => {
  it('formats numbers to significant digits', () => {
    expect(fmt(null)).toBe('—'); expect(fmt('abc')).toBe('—');
    expect(fmt(13.456)).toBe((13.5).toLocaleString());
    expect(fmt(0.98765, 2)).toBe((0.99).toLocaleString());
  });
  it('counts', () => { expect(count(undefined)).toBe('0'); expect(count(1049)).toBe((1049).toLocaleString()); });
  it('only links http(s) URLs', () => {
    expect(safeURL('https://ntrs.nasa.gov/x')).toBe('https://ntrs.nasa.gov/x');
    expect(safeURL('javascript:alert(1)')).toBe('#');
    expect(safeURL('not a url')).toBe('#');
  });
  it('links documents and pages', () => {
    expect(docLink('ab cd', 5)).toBe('/api/documents/ab%20cd#page=5');
    expect(docLink('x')).toBe('/api/documents/x');
    expect(docLink('x', 0)).toBe('/api/documents/x');
  });
  it('names investigations', () => {
    expect(invName('PSI-25')).toBe('BASS-II (PSI-25)');
    expect(invName('SAFFIRE')).toBe('SAFFIRE');
    expect(psiLink('PSI-25')).toBe('https://psi.nasa.gov/physci/repo/data/investigations/PSI-25');
    expect(psiLink('SAFFIRE')).toBe('');
  });
  it('prettifies field names', () => { expect(prettyField('condition_initial_oxygen')).toBe('initial oxygen'); });
});
