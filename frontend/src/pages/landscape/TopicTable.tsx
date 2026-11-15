import { count, invName } from '../../lib/format';
import type { Slots } from '../../lib/landscape';
import type { Cluster } from '../../lib/types';

export function TopicTable({ clusters, slots, onToggle }: { clusters: Cluster[]; slots: Slots; onToggle: (id: number) => void }) {
  return (
    <>
      <div className="table-scroll"><table><thead><tr><th>Topic</th><th>What it covers</th><th className="num">Items</th><th>Main investigations</th><th>Keywords</th></tr></thead><tbody>
        {[...clusters].sort((a, b) => b.size - a.size).map(c => (
          <tr key={c.id} tabIndex={0} style={{ cursor: 'pointer' }} aria-selected={slots.includes(c.id) ? true : undefined}
            onClick={() => onToggle(c.id)} onKeyDown={e => { if (e.key === 'Enter') onToggle(c.id); }}>
            <td><strong>{c.label}</strong></td>
            <td className="small">{c.description || ''}</td>
            <td className="num">{count(c.size)}</td>
            <td className="small">{Object.entries(c.investigations).slice(0, 3).map(([k, n]) => `${invName(k)} ${count(n)}`).join(' · ')}</td>
            <td className="small muted">{c.keywords.slice(0, 5).join(', ')}</td>
          </tr>
        ))}
      </tbody></table></div>
      <p className="hint">Click a topic to highlight it on the map.</p>
    </>
  );
}
