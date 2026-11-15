import { describe, expect, it } from 'vitest';
import { BEATS, EARTH_LIMIT, ORBIT_MIN, explain, flameLook, flameState, mixLook, orbitLimit, stageMode } from './flameStory';

describe('flame model', () => {
  it('has the quoted limits', () => {
    expect(orbitLimit(37.5)).toBeCloseTo(ORBIT_MIN);
    expect(orbitLimit(0)).toBeCloseTo(ORBIT_MIN + 7);
    expect(flameState({ gravity: 'earth', oxygen: 15, flow: 35 }).burning).toBe(false);
    expect(flameState({ gravity: 'earth', oxygen: EARTH_LIMIT, flow: 35 }).burning).toBe(true);
  });
  it('matches the story beats', () => {
    expect(flameState(BEATS[2].preset)).toMatchObject({ burning: true, weak: true, zone: 'gentle' });
    expect(flameState({ ...BEATS[2].preset, gravity: 'earth' }).burning).toBe(false);
    expect(explain({ ...BEATS[2].preset, gravity: 'earth' }, flameState({ ...BEATS[2].preset, gravity: 'earth' })).title).toBe('Out: too little oxygen for Earth');
    expect(explain({ gravity: 'orbit', oxygen: 14, flow: 100 }, flameState({ gravity: 'orbit', oxygen: 14, flow: 100 })).title).toBe('Out: blown off');
  });
  it('dims, shrinks and blues the flame at low oxygen; out means alpha 0', () => {
    const rich = flameLook({ gravity: 'earth', oxygen: 25, flow: 35 }, flameState({ gravity: 'earth', oxygen: 25, flow: 35 }));
    const lean = flameLook({ gravity: 'earth', oxygen: 16, flow: 35 }, flameState({ gravity: 'earth', oxygen: 16, flow: 35 }));
    const out = flameLook({ gravity: 'earth', oxygen: 14, flow: 35 }, flameState({ gravity: 'earth', oxygen: 14, flow: 35 }));
    expect(lean.size).toBeLessThan(rich.size);
    expect(lean.glow).toBeLessThan(rich.glow);
    expect(lean.soot).toBeLessThan(rich.soot);
    expect(out.alpha).toBe(0);
    expect(mixLook(rich, out, 0.5).alpha).toBeCloseTo(0.5);
  });
  it('streams further downstream with more flow in orbit', () => {
    const st = (flow: number) => flameLook({ gravity: 'orbit', oxygen: 21, flow }, flameState({ gravity: 'orbit', oxygen: 21, flow }));
    expect(st(80).len).toBeGreaterThan(st(35).len);
    expect(st(35).len).toBeGreaterThan(st(0).len);
  });
  it('chooses photos for steps 1-2, BASS-II for step 5, else the illustration', () => {
    expect(stageMode(0, false, false)).toBe('photos');
    expect(stageMode(1, true, false)).toBe('photos'); // gravity switch only
    expect(stageMode(1, true, true)).toBe('drawn');
    expect(stageMode(2, false, false)).toBe('drawn');
    expect(stageMode(4, false, false)).toBe('bass');
    expect(stageMode(4, true, true)).toBe('drawn');
  });
});
