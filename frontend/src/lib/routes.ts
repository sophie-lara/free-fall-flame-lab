// Hash routes: #/ask, #/coverage, ... The first path segment names the page.
export type Page = 'home' | 'ask' | 'explore' | 'coverage' | 'landscape' | 'sources' | 'upload';
const PAGES: Page[] = ['home', 'ask', 'explore', 'coverage', 'landscape', 'sources', 'upload'];

/** First segment of the router path; unknown pages (e.g. the retired #/predict) show home. */
export function pageOf(pathname: string): Page {
  const seg = pathname.replace(/^\/+/, '').split(/[/?]/)[0] || 'home';
  return (PAGES as string[]).includes(seg) ? (seg as Page) : 'home';
}

/** "Explore" is a menu of two pages: experiment coverage and the evidence landscape. */
export const isExplore = (p: Page): boolean => p === 'explore' || p === 'coverage' || p === 'landscape';

const TITLES: Record<Page, string> = {
  home: 'Combustion Atlas', ask: 'Ask', explore: 'Experiment coverage', coverage: 'Experiment coverage',
  landscape: 'Evidence landscape', sources: 'Sources', upload: 'Add to corpus',
};
export const pageTitle = (p: Page): string => `${TITLES[p]} · Combustion Atlas`;
