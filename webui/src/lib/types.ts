export type JobState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted' | 'cleanup_pending';
export type StepState = JobState | 'waiting' | 'reused' | 'skipped' | 'retrying';
export interface SourceAsset { id: string; name: string; size_bytes: number; state: 'pending' | 'uploading' | 'ready' | 'failed'; sha256: string; error: string | null; referenced?: boolean }
export interface DraftFile { key: string; source?: SourceAsset; file?: File; name: string; size: number; sent: number; state: 'pending' | 'uploading' | 'ready' | 'failed' | 'cancelled'; error?: string }
export interface RunOptions {
  chunk_seconds: number; chunk_context_seconds: number;
  minimum_candidate_seconds: number; minimum_singing_seconds: number; minimum_confidence: number;
  use_shazam: boolean; use_netease: boolean;
  recognizer_timeout: number;
}
export interface ProgressStep {
  id: string; parent_id: string | null; label: string; state: StepState; completed: number;
  total: number | null; unit: string | null; attempt: number; sequence: number; started_at: string;
  finished_at: string | null; error: string | null; elapsed_seconds?: number; waiting_seconds?: number; message?: string;
}
export interface BatchItem {
  id: string; upload_id: string; media: string; state: JobState; steps: ProgressStep[];
  error: string | null; started_at: string | null; finished_at: string | null;
  source_type?: 'upload' | 'download'; source_url?: string; can_reuse?: boolean;
}
export interface Clip { id: string; media_id: string; name: string; title: string; artist: string; duration_seconds: number; start_seconds: number; end_seconds: number; source_name: string; recognition?: unknown; title_resolution?: unknown }
export interface ClipEdit { title: string; artist: string; start_seconds: number; end_seconds: number }
export interface ClipEditProgress {
  stage: 'preparing' | 'encoding' | 'saving';
  completed_seconds: number; total_seconds: number | null; elapsed_seconds: number;
}
export interface ModelUsage { model: string; calls: number; missing_usage: number; input_tokens: number; output_tokens: number; cached_tokens: number; estimated_cny: number | null }
export interface UsageSnapshot { models: ModelUsage[]; calls: number; input_tokens: number; output_tokens: number; cached_tokens: number; estimated_cny: number; complete: boolean }
export interface JobAttempt { number: number; state: JobState; started_at: string; finished_at: string; usage: UsageSnapshot }
export interface JobStatus {
  can_complete_parts?: boolean;
  id: string; state: JobState; attempt: number; attempts: JobAttempt[]; batch: BatchItem[];
  current_index: number | null; clips: Clip[]; usage: UsageSnapshot; options: RunOptions; upload_ids: string[];
  started_at: string; finished_at: string | null; error: string | null; cleanup_error: string | null;
  usage_events: { model: string; attempt: number; media_id: string; at: string; usage: unknown }[];
}
export interface HistoryEntry {
  id: string; state: JobState; started_at: string; finished_at: string | null; medias: string[];
  clip_count: number; usage: UsageSnapshot; legacy: boolean; availability?: string; attempt: number;
}
export interface Bootstrap { version: number; defaults: RunOptions; active_job_ids: string[] }
export interface LogChunk { text: string; offset: number; complete: boolean }
export const isActive = (state?: string) => state === 'queued' || state === 'running';
