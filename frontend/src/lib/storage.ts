// Browser storage, with the same keys and formats as the previous UI.
import type { Turn } from './types';

export const CHAT_KEY = 'atlas-chat';
export const AI_KEY = 'atlas-ai';
export const SPACE_KEY = 'atlas-space';
export const UPLOADS_KEY = 'combustionAtlas.myUploads';

function safeGet(store: () => Storage, key: string): string | null {
  try { return store().getItem(key); } catch { return null; }
}
function safeSet(store: () => Storage, key: string, value: string): void {
  try { store().setItem(key, value); } catch { /* storage full or blocked */ }
}
const local = () => localStorage;
const session = () => sessionStorage;

/** The conversation survives a refresh (this tab only); finished turns only. */
export function loadChat(): Turn[] {
  try {
    const parsed: unknown = JSON.parse(safeGet(session, CHAT_KEY) || '[]');
    return Array.isArray(parsed) ? (parsed as Turn[]).filter(t => t && !t.loading) : [];
  } catch {
    return [];
  }
}
export function saveChat(turns: Turn[]): void {
  safeSet(session, CHAT_KEY, JSON.stringify(turns.filter(t => !t.loading).slice(-12)));
}

export const loadAi = (): boolean => safeGet(local, AI_KEY) !== 'off';
export const saveAi = (on: boolean): void => safeSet(local, AI_KEY, on ? 'on' : 'off');
export const loadSpace = (): boolean => safeGet(local, SPACE_KEY) !== 'off';
export const saveSpace = (on: boolean): void => safeSet(local, SPACE_KEY, on ? 'on' : 'off');

export interface MyUpload { source_id: string; filename?: string }

/** Visitor uploads are remembered in this browser so their questions can include them. */
export function myUploads(): MyUpload[] {
  try {
    const parsed: unknown = JSON.parse(safeGet(local, UPLOADS_KEY) || '[]');
    return Array.isArray(parsed) ? (parsed as MyUpload[]).slice(-10) : [];
  } catch {
    return [];
  }
}
export function rememberUpload(source_id: string, filename: string): void {
  const list = myUploads().filter(u => u.source_id !== source_id);
  list.push({ source_id, filename });
  localStorage.setItem(UPLOADS_KEY, JSON.stringify(list.slice(-10)));
}
