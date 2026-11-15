import { describe, expect, it } from 'vitest';
import { easeInOut, initialSlots, landHome, pickNearest, project, toggleSlot } from './landscape';
import type { Cluster } from './types';

describe('toggleSlot', () => {
  it('fills the first free slot', () => {
    expect(toggleSlot([1, null, 3], 7)).toEqual({ slots: [1, 7, 3], added: true, full: false });
  });
  it('freeing a slot never repaints the others', () => {
    expect(toggleSlot([1, 2, 3], 2).slots).toEqual([1, null, 3]);
  });
  it('refuses a fourth topic', () => {
    const slots = [1, 2, 3];
    expect(toggleSlot(slots, 9)).toEqual({ slots, added: false, full: true });
  });
});

describe('initialSlots', () => {
  it('highlights the three largest topics', () => {
    const c = (id: number, size: number) => ({ id, size } as Cluster);
    expect(initialSlots([c(0, 5), c(1, 50), c(2, 20), c(3, 30)])).toEqual([1, 3, 2]);
    expect(initialSlots([c(4, 1)])).toEqual([4, null, null]);
  });
});

describe('3-D camera', () => {
  const pts = [{ p3: [-1, 0, 0] as [number, number, number] }, { p3: [3, 2, 1] as [number, number, number] }];
  it('home view centres on the bounding box', () => {
    const cam = landHome(pts);
    expect(cam.target).toEqual([1, 1, 0.5]);
    expect(cam.zoom).toBeCloseTo(1.15 / 2);
    expect([cam.yaw, cam.pitch]).toEqual([0.6, 0.35]);
  });
  it('projects the target to the canvas centre', () => {
    const cam = { yaw: 0.3, pitch: 0.2, zoom: 1, target: [1, 2, 3] as [number, number, number] };
    const q = project([1, 2, 3], cam, 800, 600)!;
    expect(q.x).toBeCloseTo(400); expect(q.y).toBeCloseTo(300);
    expect(q.s).toBeCloseTo(1 / 2.8);
  });
  it('places points to the right and up without rotation', () => {
    const cam = { yaw: 0, pitch: 0, zoom: 1, target: [0, 0, 0] as [number, number, number] };
    const q = project([0.5, 0.5, 0], cam, 800, 600)!;
    expect(q.x).toBeGreaterThan(400); expect(q.y).toBeLessThan(300);
  });
  it('drops points behind the camera', () => {
    const cam = { yaw: 0, pitch: 0, zoom: 1, target: [0, 0, 0] as [number, number, number] };
    expect(project([0, 0, 2.8], cam, 800, 600)).toBeNull();
  });
  it('picks the nearest point within 12 px, preferring those drawn last', () => {
    const pts2 = [{ x: 10, y: 10, id: 'far' }, { x: 12, y: 10, id: 'near' }, { x: 100, y: 100, id: 'away' }];
    expect(pickNearest(pts2, 12, 11)?.id).toBe('near');
    expect(pickNearest(pts2, 50, 50)).toBeNull();
  });
  it('eases in and out', () => {
    expect(easeInOut(0)).toBe(0); expect(easeInOut(1)).toBe(1); expect(easeInOut(0.5)).toBeCloseTo(0.5);
  });
});
