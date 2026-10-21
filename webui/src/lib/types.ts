export type JobState = 'running' | 'succeeded' | 'failed' | 'cancelled';

export type ItemState = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface InputFile {
  name: string;
  size_bytes: number;
}

export interface BatchItem {
  media: string;
  state: ItemState;
  returncode: number | null;
  log_path: string;
  clip_count: number;
}

export interface Clip {
  name: string;
  path: string;
  title: string;
  artist: string;
  duration_seconds: number;
}

export interface UploadItem {
  key: string;
  total_bytes: number;
  transferred_bytes: number;
  state: 'uploading' | 'completed' | 'failed';
}

export interface ModelUsage {
  model: string;
  calls: number;
  missing_usage: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  estimated_cny: number | null;
}

export interface UsageSnapshot {
  models: ModelUsage[];
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  estimated_cny: number;
  complete: boolean;
}

export interface JobStatus {
  state: JobState;
  batch_complete: boolean;
  usage: UsageSnapshot;
  upload: { uploads: UploadItem[] };
  accounting_errors: string[];
  returncode: number | null;
  log_complete: boolean;
  log_path: string;
  outdir: string;
  clips: Clip[];
  started_at: string;
  finished_at: string;
  media: string;
  batch: BatchItem[];
}

export interface HistoryEntry {
  id: string;
  state: JobState;
  started_at: string;
  finished_at: string;
  outdir: string;
  medias: string[];
  clip_count: number;
  usage: UsageSnapshot;
}

export interface Bootstrap {
  version: number;
  input_dir: string;
  output_dir: string;
  max_jobs: number | null;
}

export interface LogChunk {
  text: string;
  offset: number;
  running: boolean;
  state: ItemState;
}
