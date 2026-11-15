// Topics dropdown: highlight up to three; stays open while toggling, closes outside or on Escape.
import { useEffect, useRef } from 'react';
import { LegendShape } from '../../components/common';
import { count } from '../../lib/format';
import type { Slots } from '../../lib/landscape';
import type { Cluster } from '../../lib/types';

interface Props {
  clusters: Cluster[]; slots: Slots; open: boolean;
  onOpenChange: (open: boolean) => void; onToggle: (id: number) => void; onClear: () => void;
}

export function TopicMenu({ clusters, slots, open, onOpenChange, onToggle, onClear }: Props) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => { if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) onOpenChange(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { onOpenChange(false); ref.current?.querySelector('summary')?.focus(); } };
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('click', onClick); document.removeEventListener('keydown', onKey); };
  }, [open, onOpenChange]);

  const full = !slots.includes(null);
  const n = slots.filter(x => x !== null).length;
  const sorted = [...clusters].sort((a, b) => b.size - a.size);
  return (
    <details className="topic-menu" ref={ref} open={open} onToggle={e => { const o = e.currentTarget.open; if (o !== open) onOpenChange(o); }}>
      <summary className="btn small"><span>Topics</span> <span className="muted">{n} of 3 highlighted</span> <span aria-hidden="true">▾</span></summary>
      <div className="topic-menu-panel">
        <div className="row topic-menu-head"><span className="small muted">Highlight up to three topics</span><span className="spacer" /><button type="button" className="linklike" onClick={onClear}>Clear</button></div>
        <div className="topic-menu-list" role="group" aria-label="Topics to highlight (up to three)">
          {sorted.map(c => {
            const slot = slots.indexOf(c.id);
            const disabled = full && slot < 0;
            return (
              <label key={c.id} className={`topic-opt${disabled ? ' disabled' : ''}`} title={c.description || c.keywords.join(', ')}>
                <input type="checkbox" checked={slot >= 0} disabled={disabled} onChange={() => onToggle(c.id)} />
                <span className="topic-sw"><LegendShape shape="circle" color={slot >= 0 ? `var(--s${slot + 1})` : 'var(--neutral)'} /></span>
                <span className="topic-name">{c.label}</span><span className="muted small">{count(c.size)}</span>
              </label>
            );
          })}
        </div>
      </div>
    </details>
  );
}
