'use client';
import { useState } from 'react';
import { api, type CacheCategory } from '@/lib/api';
import { errorText } from '@/lib/format';
import { Button, MaterialDialog } from './Material';

const CACHES = [
  { id: 'audio', label: '提取音频缓存', unit: '个文件' },
  { id: 'waveform', label: '波形缓存', unit: '个文件' },
  { id: 'recognition', label: 'AI 扫描与识曲缓存', unit: '条' },
] as const;

const BYTES_PER_KIB = 1024;
const SIZE_UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];

function formatSize(bytes: number): string {
  const unit = Math.min(SIZE_UNITS.length - 1, Math.floor(Math.log(Math.max(1, bytes)) / Math.log(BYTES_PER_KIB)));
  return `${(bytes / BYTES_PER_KIB ** unit).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${SIZE_UNITS[unit]}`;
}

export function CacheSettings() {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<CacheCategory[]>([]);
  const [message, setMessage] = useState(''), [error, setError] = useState('');
  const [sizes, setSizes] = useState<Record<CacheCategory, number> | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [loading, setLoading] = useState(false);
  const preview = async () => {
    setSizes(null); setPreviewError(''); setLoading(true);
    try { setSizes((await api.cachePreview()).bytes); }
    catch (cause) { setPreviewError(errorText(cause)); }
    finally { setLoading(false); }
  };
  const selectedFileBytes = sizes && selected.reduce((sum, id) => id === 'recognition' ? sum : sum + sizes[id], 0);
  const close = () => { if (!busy) setOpen(false); };
  const clear = async () => {
    setBusy(true); setError(''); setMessage('');
    try {
      const { removed } = await api.clearCaches(selected);
      setMessage(`已清除：${CACHES.filter(({ id }) => selected.includes(id))
        .map(({ id, label, unit }) => `${label} ${removed[id]} ${unit}`).join('、')}。`);
      setOpen(false);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  return <section className="settings-card">
    <h2>缓存管理</h2>
    <p className="helper">只清除所选缓存；原视频、草稿、导出文件和任务记录不受影响。</p>
    <Button variant="outlined" disabled={loading} onClick={() => {
      setSelected([]); setError(''); setOpen(true); void preview();
    }}>清除缓存</Button>
    {message && <p className="helper" role="status">{message}</p>}
    <MaterialDialog open={open} title="清除缓存" onClose={close} dismissible={!busy}>
      <p>要释放磁盘空间，优先选择提取音频和波形。提取音频只可在任务空闲时清除。</p>
      <div className="cache-options" role="group" aria-label="缓存分类">
        {CACHES.map(({ id, label }) => <label key={id}>
          <input type="checkbox" checked={selected.includes(id)} disabled={busy} onChange={event => {
            const checked = event.currentTarget.checked;
            setSelected(current => checked ? [...current, id] : current.filter(value => value !== id));
          }} />{label}{sizes && <small className="helper">{formatSize(sizes[id])}</small>}
        </label>)}
      </div>
      {loading && <p className="helper" role="status">正在统计缓存大小…</p>}
      {previewError && <p className="error" role="alert">无法读取缓存大小：{previewError}</p>}
      {selectedFileBytes !== null && <p className="helper">已选文件大小：{formatSize(selectedFileBytes)}。识别缓存按数据大小统计，不计入文件合计。</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="dialog-actions">
        <Button disabled={busy} onClick={close}>取消</Button>
        <Button variant="filled" disabled={busy || !selected.length} onClick={() => void clear()}>{busy ? '正在清除…' : '确认清除'}</Button>
      </div>
    </MaterialDialog>
  </section>;
}
