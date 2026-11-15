'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { RunOptions } from '@/lib/types';
import { errorText } from '@/lib/format';
import { Button } from './Material';
import { Parameters } from './Parameters';

export function TaskSettings({ options, onSaved }: { options: RunOptions | null; onSaved: (options: RunOptions) => void }) {
  const [draft, setDraft] = useState(options), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [saved, setSaved] = useState(false);
  useEffect(() => { setDraft(options); }, [options]);
  const save = async () => {
    if (!draft) return;
    setBusy(true); setError(''); setSaved(false);
    try { const result = await api.saveDefaults(draft); onSaved(result.options); setSaved(true); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  return <section className="settings-card task-settings">
    <p className="helper">保存后用于新任务，正在运行及续跑的任务保留原参数。</p>
    {draft && <div inert={busy}><Parameters options={draft} onChange={value => { setDraft(value); setSaved(false); }} /></div>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="dialog-actions">{saved && <span role="status">设置已保存</span>}<Button variant="outlined" disabled={!draft || busy} onClick={() => void save()}>{busy ? '正在保存…' : '保存任务参数'}</Button></div>
  </section>;
}
