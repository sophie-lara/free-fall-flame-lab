import type { CSSProperties, ReactNode } from 'react';

export function PageHead({ eyebrow, title, lead }: { eyebrow: string; title: ReactNode; lead?: string }) {
  return (
    <header className="page-head">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      {lead ? <p>{lead}</p> : null}
    </header>
  );
}

export function EmptyBox({ title, text }: { title: string; text: string }) {
  return <div className="empty"><h3>{title}</h3><p>{text}</p></div>;
}

export type ShapeName = 'circle' | 'square' | 'triangle';

/** A chart mark; the fill comes from a palette variable such as var(--s1). */
export function Shape({ shape, x, y, r, className, fill }: { shape: ShapeName; x: number; y: number; r: number; className?: string; fill?: string }) {
  const style: CSSProperties | undefined = fill ? { fill } : undefined;
  const cls = className || undefined;
  if (shape === 'square') return <rect className={cls} x={(x - r).toFixed(1)} y={(y - r).toFixed(1)} width={2 * r} height={2 * r} rx="1.5" style={style} />;
  if (shape === 'triangle') {
    const h = r * 1.15;
    return <polygon className={cls} points={`${x},${(y - h).toFixed(1)} ${(x + h).toFixed(1)},${(y + h * 0.8).toFixed(1)} ${(x - h).toFixed(1)},${(y + h * 0.8).toFixed(1)}`} style={style} />;
  }
  return <circle className={cls} cx={x.toFixed(1)} cy={y.toFixed(1)} r={r} style={style} />;
}

export function LegendShape({ shape, color }: { shape: ShapeName; color: string }) {
  return <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><Shape shape={shape} x={8} y={8} r={5.5} fill={color} /></svg>;
}

/** Positioned tooltip box used by the charts; content is React-rendered (escaped). */
export function Tooltip({ tip, id }: { tip: { left: number; top: number; content: ReactNode } | null; id?: string }) {
  return (
    <div className="tooltip" id={id} hidden={!tip} style={tip ? { left: `${tip.left}px`, top: `${tip.top}px` } : undefined}>
      {tip?.content}
    </div>
  );
}

export function Toast({ message, visible }: { message: string; visible: boolean }) {
  return <div id="toast" role="status" aria-live="polite" className={visible ? 'visible' : undefined}>{message}</div>;
}


/** On/off switch (role="switch") with a visible text label. */
export function UiSwitch({ id, on, label, text, onToggle, className }: { id: string; on: boolean; label: string; text: string; onToggle: () => void; className?: string }) {
  return (
    <span className={`ui-switch${className ? ` ${className}` : ''}`}>
      <button type="button" className="ui-switch-track" id={id} role="switch" aria-checked={on} aria-label={label} onClick={onToggle}><span className="ui-switch-knob" /></button>
      <span className={`ui-switch-label${on ? ' active' : ''}`} aria-hidden="true" onClick={onToggle}>{text}</span>
    </span>
  );
}
