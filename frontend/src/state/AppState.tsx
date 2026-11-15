// App-wide state that outlives page changes: the signed-in user, loaded data, the chat thread
// and the Explore pages' selections (as the single-page app kept them before).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiError, getCorpus, getCoverage, getLandscape, getLimits, getMe, streamAsk } from '../lib/api';
import { askRequest, historyFor } from '../lib/ask';
import { indexLandscape, EMPTY_SLOTS } from '../lib/landscape';
import type { Camera, Slots } from '../lib/landscape';
import type { Facets } from '../lib/coverage';
import { loadAi, loadChat, loadSpace, myUploads, saveAi, saveChat, saveSpace } from '../lib/storage';
import type { Corpus, Coverage, LandscapeData, Limits, Me, Turn } from '../lib/types';
import { pageOf } from '../lib/routes';

export type LandView = 'chart' | 'three' | 'table';
export interface LandUI {
  slots: Slots;
  view: LandView;
  lastMap: 'chart' | 'three';
  selected: string | null;
  menuOpen: boolean;
  flyTo: number | null;
  initialized: boolean;
  /** Bumped when an item is selected, so the detail panel scrolls into view. */
  selectNonce: number;
}
/** The selection is one cell or a whole gap band. */
export interface CellSelection { grid: string; cells: [number, number][]; gap?: number }
export interface CovUI { grid: string; facets: Facets; cell: CellSelection | null; detail: string | null }
export interface ScrollRequest { id: string; nonce: number; focus: boolean }

interface AppState {
  me: Me | null;
  setMe: (me: Me) => void;
  corpus: Corpus | null;
  reloadCorpus: () => Promise<void>;
  coverage: Coverage | null;
  coverageError: string;
  limits: Limits | null;
  landscape: LandscapeData | null;
  landscapeError: string;
  loadLandscape: () => void;
  land: LandUI;
  setLand: (patch: Partial<LandUI> | ((l: LandUI) => Partial<LandUI>)) => void;
  /** Mutable 3-D camera and spin state; kept across view switches without re-rendering. */
  land3d: { cam: Camera | null; spin: boolean | undefined };
  cov: CovUI;
  setCov: (patch: Partial<CovUI> | ((c: CovUI) => Partial<CovUI>)) => void;
  turns: Turn[];
  asking: boolean;
  draft: string;
  setDraft: (v: string) => void;
  ai: boolean;
  toggleAi: () => void;
  space: boolean;
  toggleSpace: () => void;
  newChat: () => void;
  sendQuestion: (q: string) => void;
  /** Opens the Ask page and sends the question. */
  askQuestion: (q: string) => void;
  scrollReq: ScrollRequest | null;
  toast: (message: string) => void;
  toastState: { message: string; visible: boolean };
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be used inside AppProvider');
  return v;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const pageRef = useRef(pageOf(location.pathname));
  pageRef.current = pageOf(location.pathname);

  const [me, setMe] = useState<Me | null>(null);
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [coverageError, setCoverageError] = useState('');
  const [limits, setLimits] = useState<Limits | null>(null);
  const [landscape, setLandscape] = useState<LandscapeData | null>(null);
  const [landscapeError, setLandscapeError] = useState('');
  const landLoading = useRef(false);

  const loadLimits = useCallback(async () => {
    try { setLimits(await getLimits()); } catch { setLimits(null); }
  }, []);
  const reloadCorpus = useCallback(async () => {
    try { setCorpus(await getCorpus()); } catch { setCorpus({ documents: [], totals: {} }); }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      let who: Me;
      try { who = await getMe(); } catch { who = { name: null, is_admin: false }; }
      if (!alive) return;
      setMe(who);
      await Promise.all([
        reloadCorpus(),
        getCoverage().then(c => { if (alive) setCoverage(c); }).catch((e: unknown) => {
          if (!alive) return;
          setCoverageError(e instanceof ApiError && e.status === 503
            ? 'Experiment coverage is being prepared and is not available yet.'
            : e instanceof Error ? e.message : String(e));
        }),
      ]);
    })();
    void loadLimits();
    return () => { alive = false; };
  }, [reloadCorpus, loadLimits]);

  const loadLandscape = useCallback(() => {
    if (landLoading.current) return;
    landLoading.current = true;
    getLandscape().then(d => {
      if (d.missing || !d.points?.length) setLandscapeError('The evidence landscape has not been built for this collection yet.');
      else setLandscape(indexLandscape(d));
    }).catch((e: unknown) => setLandscapeError(e instanceof Error ? e.message : String(e)));
  }, []);

  // ---- Explore selections ----
  const [land, setLandState] = useState<LandUI>({
    slots: EMPTY_SLOTS, view: 'chart', lastMap: 'chart', selected: null, menuOpen: false, flyTo: null, initialized: false, selectNonce: 0,
  });
  const setLand = useCallback((patch: Partial<LandUI> | ((l: LandUI) => Partial<LandUI>)) => {
    setLandState(l => ({ ...l, ...(typeof patch === 'function' ? patch(l) : patch) }));
  }, []);
  const land3d = useRef<{ cam: Camera | null; spin: boolean | undefined }>({ cam: null, spin: undefined }).current;
  const [cov, setCovState] = useState<CovUI>({ grid: 'flex', facets: {}, cell: null, detail: null });
  const setCov = useCallback((patch: Partial<CovUI> | ((c: CovUI) => Partial<CovUI>)) => {
    setCovState(c => ({ ...c, ...(typeof patch === 'function' ? patch(c) : patch) }));
  }, []);

  // ---- chat ----
  const [turns, setTurnsState] = useState<Turn[]>(loadChat);
  const turnsRef = useRef(turns);
  const setTurns = useCallback((fn: (ts: Turn[]) => Turn[]) => {
    turnsRef.current = fn(turnsRef.current);
    setTurnsState(turnsRef.current);
  }, []);
  const [asking, setAsking] = useState(false);
  const askingRef = useRef(false);
  const [draft, setDraft] = useState('');
  const [ai, setAi] = useState(loadAi);
  const aiRef = useRef(ai);
  const [space, setSpace] = useState(loadSpace);
  const [scrollReq, setScrollReq] = useState<ScrollRequest | null>(null);
  const requestScroll = useCallback((id: string, focus: boolean) => setScrollReq(r => ({ id, focus, nonce: (r?.nonce ?? 0) + 1 })), []);

  const toggleAi = useCallback(() => {
    if (askingRef.current) return;
    aiRef.current = !aiRef.current;
    saveAi(aiRef.current);
    setAi(aiRef.current);
  }, []);
  const toggleSpace = useCallback(() => setSpace(on => { saveSpace(!on); return !on; }), []);
  const newChat = useCallback(() => {
    if (askingRef.current) return;
    setTurns(() => []);
    setDraft('');
    saveChat([]);
  }, [setTurns]);

  const sendQuestion = useCallback(async (question: string) => {
    if (!question || askingRef.current) return;
    const turn: Turn = { id: Date.now().toString(36), question, ai: aiRef.current, loading: true, progress: [], result: null, error: '' };
    const history = historyFor(turnsRef.current, turn);
    const update = (patch: Partial<Turn> | ((t: Turn) => Partial<Turn>)) =>
      setTurns(ts => ts.map(t => (t.id === turn.id ? { ...t, ...(typeof patch === 'function' ? patch(t) : patch) } : t)));
    setTurns(ts => [...ts, turn]);
    askingRef.current = true;
    setAsking(true);
    setDraft('');
    if (pageRef.current === 'ask') requestScroll(turn.id, false);
    try {
      const body = askRequest(question, turn.ai, history, myUploads().map(u => u.source_id));
      const payload = await streamAsk(body, step => update(t => ({ progress: [...t.progress, step] })));
      update({ result: { kind: 'answer', ...payload } });
    } catch (e) {
      update({ error: e instanceof Error ? e.message : String(e) });
    }
    update({ loading: false });
    askingRef.current = false;
    setAsking(false);
    saveChat(turnsRef.current);
    await loadLimits();
    if (pageRef.current === 'ask') requestScroll(turn.id, true);
  }, [setTurns, loadLimits, requestScroll]);

  const askQuestion = useCallback((q: string) => {
    if (pageRef.current !== 'ask') navigate('/ask');
    setTimeout(() => { void sendQuestion(q); }, 0);
  }, [navigate, sendQuestion]);

  // ---- toast ----
  const [toastState, setToastState] = useState({ message: '', visible: false });
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const toast = useCallback((message: string) => {
    setToastState({ message, visible: true });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastState(t => ({ ...t, visible: false })), 4000);
  }, []);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const value = useMemo<AppState>(() => ({
    me, setMe, corpus, reloadCorpus, coverage, coverageError, limits, landscape, landscapeError, loadLandscape,
    land, setLand, land3d, cov, setCov, turns, asking, draft, setDraft, ai, toggleAi, space, toggleSpace, newChat,
    sendQuestion: (q: string) => { void sendQuestion(q); }, askQuestion, scrollReq, toast, toastState,
  }), [me, corpus, reloadCorpus, coverage, coverageError, limits, landscape, landscapeError, loadLandscape, land, setLand, land3d,
    cov, setCov, turns, asking, draft, ai, toggleAi, space, toggleSpace, newChat, sendQuestion, askQuestion, scrollReq, toast, toastState]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
