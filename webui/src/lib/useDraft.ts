'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, transfer } from './api';
import { errorText } from './format';
import type { DraftFile, SourceAsset } from './types';
import { uploadDraft } from './uploadDraft';
import { reselectDraft } from './reselectDraft';
const ORDER_KEY = 'bms-draft-order';
const restored = (file: SourceAsset): DraftFile => ({ key: file.id, source: file, name: file.name, size: file.size_bytes,
  sent: file.state === 'ready' ? file.size_bytes : 0, state: file.state === 'uploading' ? 'failed' : file.state, error: file.error ?? undefined });
async function retryUpload(file: DraftFile, upload: (file: DraftFile) => Promise<SourceAsset>, reportError: (error: string) => void) {
  try { await upload(file); }
  catch (cause) { reportError(errorText(cause)); }
}
export function useDraft() {
  const [files, setFiles] = useState<DraftFile[]>([]);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const controllers = useRef(new Map<string, AbortController>());
  const patch = useCallback((key: string, changes: Partial<DraftFile>) => setFiles((items) => items.map((item) => item.key === key ? { ...item, ...changes } : item)), []);
  const refresh = useCallback(async () => {
    try {
      const result = await api.uploads();
      const order: string[] = JSON.parse(localStorage.getItem(ORDER_KEY) ?? '[]');
      const drafts = result.files.filter((file) => !file.referenced || order.includes(file.id));
      drafts.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      setFiles(drafts.map(restored)); setError(''); setLoaded(true);
    } catch (cause) { setError(errorText(cause)); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (loaded) localStorage.setItem(ORDER_KEY, JSON.stringify(files.flatMap((file) => file.source ? [file.source.id] : []))); }, [files, loaded]);
  const add = (input: FileList | File[]) => {
    setFiles((previous) => [...previous, ...Array.from(input).map((file) => ({ key: crypto.randomUUID(), name: file.name, size: file.size, file, sent: 0, state: 'pending' as const }))]);
  };
  const reselect = (key: string, file: File) => {
    try {
      patch(key, reselectDraft(files, key, file)); setError('');
    } catch (cause) { setError(errorText(cause)); }
  };
  const upload = async (file: DraftFile): Promise<SourceAsset> => {
    const controller = new AbortController(); controllers.current.set(file.key, controller);
    try {
      return await uploadDraft(file, { signal: controller.signal, update: (changes) => patch(file.key, changes), register: api.register, transfer });
    } finally { controllers.current.delete(file.key); }
  };
  const remove = async (file: DraftFile) => {
    try {
      controllers.current.get(file.key)?.abort();
      if (file.source && !file.source.referenced) await api.removeUpload(file.source.id);
      setFiles((items) => items.filter((value) => value.key !== file.key));
    } catch (cause) { setError(errorText(cause)); }
  };
  const move = (key: string, delta: number) => setFiles((items) => {
    const index = items.findIndex((item) => item.key === key), target = index + delta;
    if (target < 0 || target >= items.length) return items;
    const copy = [...items]; [copy[index], copy[target]] = [copy[target], copy[index]]; return copy;
  });
  const reuse = async (ids: string[]) => {
    const { files: sources } = await api.uploads();
    setFiles(ids.map((id) => { const source = sources.find((item) => item.id === id); if (!source) throw new Error('任务源文件已缺失'); return restored(source); }));
  };
  return { files, error, add, upload, retry: (file: DraftFile) => retryUpload(file, upload, setError), reselect, remove, move, reuse, refresh, clear: () => setFiles([]),
    cancel: (key: string) => controllers.current.get(key)?.abort() };
}
