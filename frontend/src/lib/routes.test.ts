import { describe, expect, it } from 'vitest';
import { isExplore, pageOf, pageTitle } from './routes';

describe('routes', () => {
  it('maps hash paths to pages', () => {
    expect(pageOf('/')).toBe('home');
    expect(pageOf('/ask')).toBe('ask');
    expect(pageOf('/landscape')).toBe('landscape');
    expect(pageOf('/ask/extra')).toBe('ask');
    expect(pageOf('/predict')).toBe('home');
  });
  it('groups Explore pages and titles them', () => {
    expect(isExplore('explore') && isExplore('coverage') && isExplore('landscape')).toBe(true);
    expect(isExplore('ask')).toBe(false);
    expect(pageTitle('explore')).toBe('Experiment coverage · Combustion Atlas');
  });
});
