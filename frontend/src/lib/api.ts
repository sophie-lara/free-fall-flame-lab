// Typed client for this server's /api. Same paths, bodies and error handling as before.
import type {
  AskPayload, AskRequest, Corpus, Coverage, Landscape, Limits, Me, PendingUpload, ProgressEvent, UploadResponse,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function errorText(body: unknown): string | undefined {
  if (body && typeof body === 'object' && 'error' in body) {
    const e = (body as { error?: unknown }).error;
    if (typeof e === 'string' && e) return e;
  }
  return undefined;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  let body: unknown = {};
  try { body = await response.json(); } catch { /* non-JSON error page */ }
  if (!response.ok) throw new ApiError(errorText(body) || `Request failed (${response.status})`, response.status);
  return body as T;
}

export const postJSON = <T>(path: string, body: unknown): Promise<T> =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export const getMe = () => api<Me>('/api/me');
export const getLimits = () => api<Limits>('/api/limits');
export const getCorpus = () => api<Corpus>('/api/corpus');
export const getCoverage = () => api<Coverage>('/api/coverage');
export const getLandscape = () => api<Landscape>('/api/landscape');
export const getPendingUploads = () => api<{ pending: PendingUpload[] }>('/api/uploads/pending');
export const approveUpload = (source_id: string, investigation: string) => postJSON<unknown>('/api/uploads/approve', { source_id, investigation });
export const deleteUpload = (source_id: string) => postJSON<unknown>('/api/uploads/delete', { source_id });
export const uploadPdf = (params: URLSearchParams, headers: Record<string, string>, file: File) =>
  api<UploadResponse>(`/api/upload?${params}`, { method: 'POST', headers, body: file });

// ---------- NDJSON streaming ----------
export type StreamEvent =
  | (ProgressEvent & { type: 'progress' })
  | ({ type: 'result' } & AskPayload)
  | { type: 'error'; error?: string };

/** Splits a byte stream of newline-delimited JSON into parsed objects; bad lines are skipped. */
export function createNdjsonParser(onEvent: (event: Record<string, unknown>) => void) {
  let buffer = '';
  const handle = (line: string) => {
    if (!line.trim()) return;
    let event: unknown;
    try { event = JSON.parse(line); } catch { return; }
    if (event && typeof event === 'object') onEvent(event as Record<string, unknown>);
  };
  return {
    push(chunk: string) {
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      lines.forEach(handle);
    },
    end() { handle(buffer); buffer = ''; },
  };
}

/** Streams progress from /api/ask/stream; falls back to /api/ask when the route is absent. */
export async function streamAsk(body: AskRequest, onProgress: (step: ProgressEvent) => void): Promise<AskPayload> {
  const response = await fetch('/api/ask/stream', {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (response.status === 404) return postJSON<AskPayload>('/api/ask', body);
  if (!response.ok || !response.body) {
    let msg = `Request failed (${response.status})`;
    try { msg = errorText(await response.json()) || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let result: AskPayload | null = null;
  const parser = createNdjsonParser(event => {
    if (event.type === 'progress') onProgress(event as unknown as ProgressEvent);
    else if (event.type === 'result') {
      const { type: _type, ...payload } = event;
      void _type;
      result = payload as AskPayload;
    } else if (event.type === 'error') {
      throw new Error((typeof event.error === 'string' && event.error) || 'The request failed.');
    }
  });
  for (;;) {
    const { value, done } = await reader.read();
    parser.push(decoder.decode(value || new Uint8Array(), { stream: !done }));
    if (done) { parser.end(); break; }
  }
  if (!result) throw new Error('The connection closed before the answer arrived. Please try again.');
  return result;
}
