// Evidence landscape: highlight slots and the 3-D camera (canvas, no libraries).
import type { Cluster, Landscape, LandscapeData, LandPoint, Vec3 } from './types';

export type Slots = (number | null)[];
export const EMPTY_SLOTS: Slots = [null, null, null];

/**
 * Toggles a topic in the three highlight slots. Freeing a slot never repaints the others, and
 * a new topic takes the first free slot. When all slots are full the selection is unchanged.
 */
export function toggleSlot(slots: Slots, id: number): { slots: Slots; added: boolean; full: boolean } {
  const at = slots.indexOf(id);
  if (at >= 0) { const next = [...slots]; next[at] = null; return { slots: next, added: false, full: false }; }
  const free = slots.indexOf(null);
  if (free < 0) return { slots, added: false, full: true };
  const next = [...slots]; next[free] = id;
  return { slots: next, added: true, full: false };
}

/** The three largest topics, highlighted when the page first opens. */
export function initialSlots(clusters: Cluster[]): Slots {
  const slots: Slots = [...EMPTY_SLOTS];
  [...clusters].sort((a, b) => b.size - a.size).slice(0, 3).forEach((c, i) => { slots[i] = c.id; });
  return slots;
}

export function indexLandscape(d: Landscape): LandscapeData {
  return {
    ...d,
    byId: Object.fromEntries(d.points.map(p => [p.id, p])),
    byCluster: Object.fromEntries(d.clusters.map(c => [c.id, c])),
  };
}

export interface Camera { yaw: number; pitch: number; zoom: number; target: Vec3 }

/** Home view: centred on the middle of the cloud's bounding box, so outlying topics stay in frame. */
export function landHome(points: Pick<LandPoint, 'p3'>[]): Camera {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const p of points) for (let i = 0; i < 3; i++) { lo[i] = Math.min(lo[i], p.p3[i]); hi[i] = Math.max(hi[i], p.p3[i]); }
  const radius = Math.max(...hi.map((v, i) => v - lo[i])) / 2 || 1;
  return { yaw: 0.6, pitch: 0.35, zoom: 1.15 / radius, target: [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2] };
}

export interface Projected { x: number; y: number; s: number; z: number }

/** Perspective projection: yaw about the vertical axis, then pitch; null when behind the camera. */
export function project(p3: Vec3, c: Camera, W: number, H: number): Projected | null {
  const x0 = p3[0] - c.target[0], y0 = p3[1] - c.target[1], z0 = p3[2] - c.target[2];
  const cy = Math.cos(c.yaw), sy = Math.sin(c.yaw), cp = Math.cos(c.pitch), sp = Math.sin(c.pitch);
  const x1 = cy * x0 + sy * z0, z1 = -sy * x0 + cy * z0;
  const y2 = cp * y0 - sp * z1, z2 = sp * y0 + cp * z1;
  const dist = 2.8 / c.zoom, depth = dist - z2;
  if (depth < 0.08) return null;
  const f = Math.min(W, H) * 0.95 / depth;
  return { x: W / 2 + x1 * f, y: H / 2 - y2 * f, s: 1 / depth, z: z2 };
}

/** Nearest projected point within 12 px of (mx, my), preferring points drawn last (nearest). */
export function pickNearest<T extends { x: number; y: number }>(projected: T[], mx: number, my: number): T | null {
  let best: T | null = null, bestD = 12 * 12;
  for (let i = projected.length - 1; i >= 0; i--) {
    const q = projected[i], dx = q.x - mx, dy = q.y - my, dd = dx * dx + dy * dy;
    if (dd < bestD) { best = q; bestD = dd; }
  }
  return best;
}

export const easeInOut = (t: number): number => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
export const clampZoom = (z: number): number => Math.min(10, Math.max(0.5, z));
export const clampPitch = (p: number): number => Math.max(-1.5, Math.min(1.5, p));

export const KIND_SHAPE = { passage: 'circle', figure: 'square', table: 'triangle' } as const;
export const KIND_LABEL = { passage: 'Text passage', figure: 'Figure description', table: 'Reviewed table' } as const;
