// Formatting and link helpers shared across pages.

export const NAMES: Record<string, string> = {
  'PSI-25': 'BASS-II', 'PSI-26': 'BASS', 'PSI-69': 'FLEX', 'PSI-68': 'FLEX-2', 'PSI-98': 'Saffire-I',
  'PSI-99': 'Saffire-II', 'PSI-100': 'Saffire-III', 'PSI-102': 'SAME', 'PSI-101': 'SAME-R',
};

/** Up to `digits` significant digits, or an em dash when missing. */
export function fmt(v: unknown, digits = 3): string {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return Number(v).toLocaleString(undefined, { maximumSignificantDigits: digits });
}

export const count = (v: unknown): string => Number(v ?? 0).toLocaleString();

/** Only http(s) URLs are linked; anything else becomes "#". */
export function safeURL(v: unknown): string {
  try {
    const u = new URL(String(v));
    return ['https:', 'http:'].includes(u.protocol) ? u.href : '#';
  } catch {
    return '#';
  }
}

export const docLink = (sourceId: string, page?: number | string | null): string =>
  `/api/documents/${encodeURIComponent(sourceId)}${page ? `#page=${encodeURIComponent(page)}` : ''}`;

export const invName = (id: string): string => (NAMES[id] ? `${NAMES[id]} (${id})` : id);

export const prettyField = (f: unknown): string => String(f || '').replace(/^condition_/, '').replace(/_/g, ' ');

export const plural = (n: number, word: string, many = `${word}s`): string => (n === 1 ? word : many);

export const psiLink = (id: string): string =>
  /^PSI-\d+$/.test(id) ? `https://psi.nasa.gov/physci/repo/data/investigations/${id}` : '';

export const prefersReducedMotion = (): boolean =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export const scrollBehavior = (): ScrollBehavior => (prefersReducedMotion() ? 'auto' : 'smooth');
