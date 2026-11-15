// Add to corpus: the administrator's form and pending visitor uploads, or the visitor form.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { EmptyBox, PageHead } from '../components/common';
import { useApp } from '../state/AppState';
import { approveUpload, deleteUpload, getMe, getPendingUploads, uploadPdf } from '../lib/api';
import { myUploads, rememberUpload } from '../lib/storage';
import type { PendingUpload, UploadResponse } from '../lib/types';
import { useNavigate } from 'react-router-dom';

type Status =
  | { kind: 'none' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string; alert: boolean }
  | { kind: 'done'; r: UploadResponse };

const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

function PendingUploads() {
  const { toast, reloadCorpus } = useApp();
  const [pending, setPending] = useState<PendingUpload[] | null>(null);
  const [error, setError] = useState('');
  const [inv, setInv] = useState<Record<string, string>>({});
  const load = useCallback(async () => {
    try { setPending((await getPendingUploads()).pending); setError(''); } catch (e) { setError(errMsg(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (error) return <section className="section" id="pending-uploads"><div className="error">{error}</div></section>;
  if (!pending) return <section className="section" id="pending-uploads"><p className="loading">Loading visitor uploads…</p></section>;
  const approve = async (id: string) => {
    const investigation = (inv[id] || '').trim();
    if (!investigation) { toast('Enter an investigation ID to approve.'); return; }
    try { await approveUpload(id, investigation); toast('Approved and added to the shared collection.'); await reloadCorpus(); void load(); } catch (e) { toast(errMsg(e)); }
  };
  const remove = async (id: string) => {
    if (!confirm('Delete this upload and its index entries?')) return;
    try { await deleteUpload(id); toast('Upload deleted.'); void load(); } catch (e) { toast(errMsg(e)); }
  };
  return (
    <section className="section" id="pending-uploads">
      <div className="section-head"><h2>Visitor uploads awaiting review</h2><span className="muted small">{pending.length} pending</span></div>
      {pending.length ? pending.map(p => (
        <div key={p.source_id} className="card row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220 }}><strong>{p.filename}</strong><div className="muted small">{p.pages} pages · {p.passages} passages · uploaded {p.uploaded_at}</div></div>
          <input className="pend-inv" aria-label={`Investigation ID for ${p.filename}`} placeholder="Investigation ID, e.g. PSI-26" maxLength={79} value={inv[p.source_id] || ''} onChange={e => setInv(v => ({ ...v, [p.source_id]: e.target.value }))} />
          <button className="btn primary" type="button" onClick={() => void approve(p.source_id)}>Approve</button>
          <button className="btn" type="button" onClick={() => void remove(p.source_id)}>Delete</button>
        </div>
      )) : <p className="muted">No visitor uploads are waiting.</p>}
    </section>
  );
}

export function Upload() {
  const { me, setMe, reloadCorpus, setDraft } = useApp();
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>({ kind: 'none' });
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const invRef = useRef<HTMLInputElement>(null);
  const urlRef = useRef<HTMLInputElement>(null);
  const embedRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const limits = me?.upload_limits || {};

  if (!me?.can_upload) {
    return <><PageHead eyebrow="Contribute" title="Add to corpus" lead="Upload a NASA report or paper (PDF)." /><EmptyBox title="Uploads are closed" text="Only the project administrator can add documents right now." /></>;
  }
  const visitor = !me.is_admin;
  const mine = myUploads();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const maxMb = visitor ? Number(limits.max_mb) : 80;
    if (file.size > maxMb * 1024 * 1024) { setStatus({ kind: 'error', message: `The PDF is larger than ${visitor ? limits.max_mb : 80} MB.`, alert: false }); return; }
    const params = new URLSearchParams({ filename: file.name });
    if (!visitor) {
      params.set('investigation', invRef.current?.value.trim() || '');
      params.set('source_url', urlRef.current?.value.trim() || '');
      params.set('embed', embedRef.current?.checked ? '1' : '0');
    }
    const headers: Record<string, string> = { 'Content-Type': 'application/pdf' };
    if (codeRef.current) headers['X-Upload-Code'] = codeRef.current.value;
    setBusy(true); setStatus({ kind: 'loading' });
    try {
      const r = await uploadPdf(params, headers, file);
      if (r.quarantined) {
        rememberUpload(r.source_id, r.filename);
        setMe(await getMe());
      } else {
        await reloadCorpus();
      }
      setStatus({ kind: 'done', r });
    } catch (err) {
      setStatus({ kind: 'error', message: errMsg(err), alert: true });
    }
    setBusy(false);
  };

  let statusView = null;
  if (status.kind === 'loading') statusView = <p className="loading" style={{ padding: '16px 0' }}>Extracting and indexing pages…</p>;
  else if (status.kind === 'error') statusView = <div className="error" role={status.alert ? 'alert' : undefined}>{status.message}</div>;
  else if (status.kind === 'done' && status.r.quarantined) {
    const r = status.r;
    statusView = <>
      <p className="notice">Indexed <strong>{r.filename}</strong>: {r.physical_pages} pages, {r.chunks_added} passages. It is private to this browser until reviewed. {r.uploads_left_today} upload{r.uploads_left_today === 1 ? '' : 's'} left today.</p>
      <button className="btn" type="button" id="ask-upload" onClick={() => { setDraft(''); navigate('/ask'); }}>Ask about this document →</button>
    </>;
  } else if (status.kind === 'done') {
    const r = status.r;
    statusView = <p className="notice">{r.status === 'unchanged' ? 'Already indexed — nothing changed.' : <>Added <strong>{r.filename}</strong> ({r.investigation_id}): {r.physical_pages} pages, {r.chunks_added} passages, {r.embedded_chunks} with semantic search.</>}</p>;
  }

  return (
    <>
      {visitor
        ? <PageHead eyebrow="Contribute" title="Add a document" lead="Upload a PDF and ask questions about it. It is private to you (this browser) until an administrator reviews it and adds it to the shared collection." />
        : <PageHead eyebrow="Administrator" title="Add to corpus" lead="Upload a NASA report or paper (PDF). Pages are extracted and added without changing existing documents." />}
      <form className="card" id="upload-form" style={{ maxWidth: 720 }} onSubmit={e => void submit(e)}>
        <div className="field"><label htmlFor="u-file">PDF file ({visitor ? `up to ${limits.max_mb ?? ''} MB and ${limits.max_pages ?? ''} pages` : 'up to 80 MB'})</label><input id="u-file" ref={fileRef} type="file" accept="application/pdf,.pdf" required /></div>
        {visitor ? null : <>
          <div className="field"><label htmlFor="u-inv">Investigation ID</label><input id="u-inv" ref={invRef} required maxLength={79} placeholder="e.g. PSI-25 or SAFFIRE-II" style={{ width: '100%' }} /></div>
          <div className="field"><label htmlFor="u-url">Source URL (optional)</label><input id="u-url" ref={urlRef} type="url" placeholder="https://ntrs.nasa.gov/citations/…" style={{ width: '100%' }} /></div>
          <div className="field"><label className="check"><input id="u-embed" ref={embedRef} type="checkbox" defaultChecked /><span>Enable semantic search (creates vector embeddings so passages can be found by meaning, not just keywords)</span></label></div>
        </>}
        {visitor && me.upload_code_required ? <div className="field"><label htmlFor="u-code">Upload code</label><input id="u-code" ref={codeRef} type="password" autoComplete="off" required style={{ width: '100%' }} /></div> : null}
        <button className="btn primary" type="submit" disabled={busy}>{visitor ? 'Upload and index' : 'Add to corpus'}</button>
        <p className="hint">{visitor
          ? `Each visitor can upload ${limits.per_day ?? ''} documents per day${limits.remaining_today != null ? ` (${limits.remaining_today} left today)` : ''}; uploads also count toward the site's daily AI limit. Text is extracted and indexed for semantic search; figures are not described.`
          : 'Text search and cited answers work immediately; figures in uploads are not described automatically.'}</p>
        <div id="u-status" aria-live="polite">{statusView}</div>
      </form>
      {visitor && mine.length ? (
        <section className="card section" style={{ maxWidth: 720 }}><h3 style={{ marginTop: 0 }}>Your uploads (included in your questions)</h3>
          <ul className="plain">{mine.map(u => <li key={u.source_id}>{u.filename || u.source_id}</li>)}</ul>
          <p className="hint">Only questions from this browser search these documents.</p></section>
      ) : null}
      {visitor ? null : <PendingUploads />}
    </>
  );
}
