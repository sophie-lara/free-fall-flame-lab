// API payload types, inferred from how the UI uses /api responses.

export interface UploadLimits {
  max_mb?: number;
  max_pages?: number;
  per_day?: number;
  remaining_today?: number | null;
}

export interface Me {
  name: string | null;
  is_admin: boolean;
  can_upload?: boolean;
  visitor_upload?: boolean;
  upload_code_required?: boolean;
  upload_limits?: UploadLimits;
}

export interface Limits {
  enabled: boolean;
  exempt?: boolean;
  remaining_today?: number | null;
  next_available_in_s?: number | null;
}

export interface CorpusDocument {
  source_id: string;
  filename: string;
  source_url?: string | null;
  investigation_ids?: string[];
  pages?: number;
  figures?: number;
}

export interface CorpusTotals {
  documents?: number;
  investigations?: number;
  pages?: number;
  figures?: number;
}

export interface Corpus {
  documents: CorpusDocument[];
  totals: CorpusTotals;
}

// ---------- coverage ----------
export interface CoverageField { key: string; label: string; unit: string | null; count: number }
export interface CoverageFamily { key: string; label: string; count: number; investigation_ids?: string[] }

export interface RunOutcome { value: number | null; raw: string; unit?: string | null }

export interface CoverageRecord {
  id: string;
  investigation_id: string;
  family: string;
  test_id: string;
  material?: string | null;
  geometry?: string | null;
  gravity?: string | null;
  review_status?: string;
  outcomes?: Record<string, RunOutcome>;
  source?: { file?: string; record?: number | string | null; url?: string | null };
  raw?: Record<string, string>;
  oxygen_pct?: number | null;
  flow_cm_s?: number | null;
  pressure_kpa?: number | null;
  [field: string]: unknown;
}

export interface ProposedTest {
  investigation_id: string;
  test_id: string;
  table: string;
  page: number;
  document_id?: string | null;
  source_url?: string | null;
  fields?: Record<string, number | null | undefined>;
  fuel?: string | null;
  suppressant?: string | null;
  conversions?: string[];
}

export interface Bin { key: string; label: string; lo: number | null; hi: number | null }
export interface Axis { key: string; label: string; unit: string | null; bins: Bin[] }
export interface FacetOption { key: string; label: string }
export interface Facet { key: string; label: string; options: FacetOption[] }

export type CellClass = 'strong' | 'moderate' | 'sparse' | 'planned' | 'gap';

export interface Cell {
  x: number;
  y: number;
  ids: string[];
  planned_ids: number[];
  outcomes: Record<string, number>;
  reviewed: number;
  observed: number;
  planned: number;
  neighbours: number;
  class: CellClass;
}

export interface GridGap {
  status: 'planned' | 'unplanned';
  label: string;
  detail?: string;
  cells: [number, number][];
  planned: number;
}

export interface GridView {
  cells: Cell[];
  gaps?: GridGap[];
  totals: { observed: number; planned: number; cells_with_runs: number; cells: number };
}

export interface Grid {
  key: string;
  label: string;
  description: string;
  x: Axis;
  y: Axis;
  facets: Facet[];
  has_planned: boolean;
  views: Record<string, GridView>;
  notes?: string[];
}

export interface Coverage {
  records: CoverageRecord[];
  fields?: CoverageField[];
  families?: CoverageFamily[];
  notes?: string[];
  proposed?: ProposedTest[];
  grids?: Grid[];
  cell_classes?: Partial<Record<CellClass, string>>;
}

// ---------- landscape ----------
export type LandKind = 'passage' | 'figure' | 'table';
export type Vec3 = [number, number, number];

export interface LandPoint {
  id: string;
  source_id: string;
  filename: string;
  page: number | null;
  investigation: string | null;
  kind: LandKind;
  label: string | null;
  snippet: string;
  x: number;
  y: number;
  p3: Vec3;
  cluster: number;
  core: boolean;
  neighbors: string[];
}

export interface Cluster {
  id: number;
  size: number;
  keywords: string[];
  label: string;
  description?: string | null;
  x: number;
  y: number;
  p3: Vec3;
  investigations: Record<string, number>;
}

export interface Landscape {
  missing?: boolean;
  points: LandPoint[];
  clusters: Cluster[];
  noise: number;
  params?: { projection?: string; clustering?: string; neighbors?: string };
  notes?: string[];
  generated_at?: string | null;
  stale?: boolean;
}

export interface LandscapeData extends Landscape {
  byId: Record<string, LandPoint>;
  byCluster: Record<number, Cluster>;
}

// ---------- ask ----------
export interface Note { kind: string; text: string }

export interface RowValue {
  field: string;
  value?: string | number | null;
  unit?: string | null;
  original?: string | null;
  notes?: Note[];
}

export interface RecordCard {
  kind?: 'row' | 'table' | string;
  test_id?: string;
  table_title?: string;
  evidence_kind?: string;
  evidence_kinds?: Record<string, number>;
  review_action?: string;
  locator?: string;
  provenance?: string;
  values?: RowValue[];
  caveats?: string[];
  open_questions?: unknown[] | number;
  match?: { query: string; field: string; conversion?: string | null }[];
  rows?: number;
  notes?: (Note & { rows?: number })[];
}

export interface Visual { kind: string; label: string; caption?: string }

export interface SearchResult {
  chunk_id: string;
  source_id: string;
  filename: string;
  physical_page?: number | null;
  investigation_id?: string | null;
  text?: string;
  record_card?: RecordCard | null;
  record_row?: unknown;
  visual?: Visual | null;
  crop_url?: string | null;
}

export interface Support { chunk_id: string; quote: string }
export interface Claim { text: string; supports: Support[] }
export interface Answer { status: string; claims: Claim[]; limitations?: string[] }

export interface AskPayload {
  question?: string;
  method?: string;
  results?: SearchResult[];
  answer?: Answer | null;
  limited?: { reason: string } | null;
  answer_unavailable?: string | null;
  retrieval_fallback?: string | null;
  answered_by?: { model: string; provider: string; backup: boolean } | null;
}

export interface AskResult extends AskPayload { kind: 'answer' }

export interface ProgressEvent { type?: 'progress'; stage: string; message: string; elapsed_s: number }

export interface Turn {
  id: string;
  question: string;
  ai: boolean;
  loading: boolean;
  progress: ProgressEvent[];
  result: AskResult | null;
  error: string;
}

export interface HistoryItem { question: string; answer: string }

export interface AskRequest {
  question: string;
  history: HistoryItem[];
  method: 'hybrid' | 'keyword';
  generate_answer: boolean;
  allow_provider_calls: boolean;
  include_sources: string[];
}

export interface PendingUpload { source_id: string; filename: string; pages: number; passages: number; uploaded_at: string }

export interface UploadResponse {
  quarantined?: boolean;
  source_id: string;
  filename: string;
  status?: string;
  investigation_id?: string;
  physical_pages?: number;
  chunks_added?: number;
  embedded_chunks?: number;
  uploads_left_today?: number;
}
