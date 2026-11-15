'use client';
import { useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { Button, MaterialDialog } from './Material';

export interface ClearOutcome { readonly removedJobs: number; readonly removedLegacy: number }

export async function clearHistory(): Promise<ClearOutcome> {
  return api.clearHistory();
}

/** Kept as a component so the settings card owns the confirm dialog and result notice. */
export function ClearHistoryButton() {
  const [open, setOpen] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  const confirm = async () => {
    try {
      const outcome = await clearHistory();
      setMessage(`已清除 ${outcome.removedJobs} 条任务记录和 ${outcome.removedLegacy} 条旧结果记录。`);
      setError('');
    } catch (cause) { setError(errorText(cause)); }
    setOpen(false);
  };
  return <>
    <Button variant="outlined" onClick={() => setOpen(true)}>清除任务记录</Button>
    {message && <p className="helper" role="status">{message}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <MaterialDialog open={open} title="清除任务记录？" onClose={() => setOpen(false)}>
      <p>只删除任务记录和旧结果索引。已导出的视频、导入的素材和累计用量都保留。</p>
      <div className="dialog-actions"><Button onClick={() => setOpen(false)}>取消</Button><Button variant="filled" onClick={() => void confirm()}>确认清除</Button></div>
    </MaterialDialog>
  </>;
}
