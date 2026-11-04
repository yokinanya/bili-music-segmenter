import type { DraftFile, SourceAsset } from './types';
import { errorText } from './format';

interface UploadContext {
  readonly signal: AbortSignal;
  readonly update: (changes: Partial<DraftFile>) => void;
  readonly register: (file: File) => Promise<SourceAsset>;
  readonly transfer: (source: SourceAsset, file: File, options: { update: (bytes: number) => void; signal: AbortSignal }) => Promise<SourceAsset>;
}
export async function uploadDraft(file: DraftFile, context: UploadContext): Promise<SourceAsset> {
  if (file.state === 'ready' && file.source) return file.source;
  if (!file.file) throw new Error(`请重新选择“${file.name}”以重试上传`);
  context.update({ state: 'uploading', error: undefined });
  try {
    const source = file.source ?? await context.register(file.file);
    context.update({ source });
    const result = await context.transfer(source, file.file, { update: (sent) => context.update({ sent }), signal: context.signal });
    context.update({ source: result, state: 'ready', sent: file.size });
    return result;
  } catch (cause) {
    context.update({ state: context.signal.aborted ? 'cancelled' : 'failed', error: errorText(cause) });
    throw cause;
  }
}
