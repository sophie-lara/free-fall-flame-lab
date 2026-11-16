import type { StepIconKind } from '../../lib/ask';

export const SendIcon = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
);

const SearchIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.8" /><path d="M10.4 10.4 14 14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
);
const WriteIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 13l1-3.5L11 2.5 13.5 5 6.5 12z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>
);
export const CheckIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
export const DotIcon = () => (
  <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3" fill="currentColor" /></svg>
);

export function StepIcon({ kind }: { kind: StepIconKind }) {
  if (kind === 'search') return <SearchIcon />;
  if (kind === 'write') return <WriteIcon />;
  if (kind === 'check') return <CheckIcon />;
  return <DotIcon />;
}
