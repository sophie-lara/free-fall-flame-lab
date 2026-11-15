import type { StepIconKind } from '../../lib/ask';

export const SendIcon = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
);

export const LogIcon = () => (
  <svg viewBox="0 0 20 12" width="20" height="12" aria-hidden="true"><rect x="1" y="2" width="15" height="8" rx="4" fill="#9a6232" /><ellipse cx="16" cy="6" rx="3" ry="4" fill="#d9a066" /><ellipse cx="16" cy="6" rx="1.4" ry="2" fill="none" stroke="#9a6232" strokeWidth=".8" /></svg>
);
const FlameIcon = () => (
  <svg viewBox="0 0 12 16" width="12" height="16" aria-hidden="true"><path d="M6 1c1 3 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 1.5.8 2.5 1.8 2.5C4 6 5 3 6 1z" fill="#ef6a2a" /><path d="M6 8c.6 1.4 2.2 2.2 2.2 4a2.2 2.2 0 0 1-4.4 0c0-1 .6-1.7 1.1-2.2C5 9 5.6 8.7 6 8z" fill="#ffc94a" /></svg>
);
const CheckIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.8" /><path d="M10.4 10.4 14 14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
);
export const DotIcon = () => (
  <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3" fill="currentColor" /></svg>
);

export function StepIcon({ kind }: { kind: StepIconKind }) {
  if (kind === 'log') return <LogIcon />;
  if (kind === 'flame') return <FlameIcon />;
  if (kind === 'check') return <CheckIcon />;
  return <DotIcon />;
}
