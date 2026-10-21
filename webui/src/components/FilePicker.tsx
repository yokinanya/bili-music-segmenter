'use client';

import { useMemo, useState } from 'react';
import type { InputFile } from '@/lib/types';

interface Props {
  directory: string;
  files: InputFile[];
  loading: boolean;
  error: string | null;
  /** Selected names in execution order; the order matters for batch runs. */
  selected: string[];
  disabled: boolean;
  onChange: (next: string[]) => void;
  onRefresh: () => void;
  filterInputRef?: React.Ref<HTMLInputElement>;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KiB', 'MiB', 'GiB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

export function FilePicker({
  directory,
  files,
  loading,
  error,
  selected,
  disabled,
  onChange,
  onRefresh,
  filterInputRef,
}: Props) {
  const [filter, setFilter] = useState('');
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const visible = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return query ? files.filter((file) => file.name.toLowerCase().includes(query)) : files;
  }, [files, filter]);

  const toggle = (name: string) => {
    if (disabled) return;
    onChange(selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name]);
  };

  const move = (from: number, to: number) => {
    if (to < 0 || to >= selected.length || from === to) return;
    const next = [...selected];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  };

  const everythingSelected = files.length > 0 && files.every((file) => selected.includes(file.name));

  return (
    <section className="card" aria-labelledby="pick-title">
      <div className="card-head">
        <h2 id="pick-title">选择输入文件</h2>
        <div className="card-actions">
          <button type="button" className="btn ghost" onClick={onRefresh} disabled={loading}>
            {loading ? '读取中…' : '刷新列表'}
          </button>
        </div>
      </div>
      <p className="hint">
        只处理输入目录 <code>{directory || 'input/'}</code> 中的媒体文件，其他文件会被忽略。
      </p>

      {files.length > 0 && (
        <div className="picker-tools">
          <label className="visually-hidden" htmlFor="file-filter">
            筛选文件
          </label>
          <input
            ref={filterInputRef}
            id="file-filter"
            type="search"
            className="input compact"
            placeholder="筛选文件名"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <button
            type="button"
            className="btn ghost"
            disabled={disabled}
            onClick={() => onChange(everythingSelected ? [] : files.map((file) => file.name))}
          >
            {everythingSelected ? '全部取消' : '全选'}
          </button>
          <span className="muted small" aria-live="polite">
            已选 {selected.length} / {files.length}
          </span>
        </div>
      )}

      {error ? (
        <p className="notice danger" role="alert">
          读取输入目录失败：{error}
          <button type="button" className="btn ghost small" onClick={onRefresh} disabled={loading}>
            重试
          </button>
        </p>
      ) : loading && files.length === 0 ? (
        <p className="muted">正在读取输入目录…</p>
      ) : files.length === 0 ? (
        <p className="empty">输入目录中还没有可处理的媒体文件。放入视频后点「刷新列表」。</p>
      ) : (
        <ul className="file-list" aria-label="输入文件">
          {visible.map((file) => {
            const checked = selected.includes(file.name);
            return (
              <li key={file.name} className={checked ? 'file-item checked' : 'file-item'}>
                <label>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={disabled}
                    onChange={() => toggle(file.name)}
                  />
                  <span className="file-name">{file.name}</span>
                  <span className="file-size muted">{formatSize(file.size_bytes)}</span>
                </label>
              </li>
            );
          })}
          {visible.length === 0 && <li className="muted empty">没有匹配的文件</li>}
        </ul>
      )}

      {selected.length > 1 && (
        <div className="queue">
          <h3>
            执行顺序 <span className="muted small">（{selected.length} 个文件，依次处理）</span>
          </h3>
          <ol>
            {selected.map((name, index) => (
              <li
                key={name}
                draggable={!disabled}
                onDragStart={() => setDragIndex(index)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (dragIndex !== null) move(dragIndex, index);
                  setDragIndex(null);
                }}
                onDragEnd={() => setDragIndex(null)}
                className={dragIndex === index ? 'dragging' : undefined}
              >
                <span className="grip" aria-hidden="true">
                  ⠿
                </span>
                <span className="file-name">{name}</span>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => move(index, index - 1)}
                  disabled={index === 0 || disabled}
                  aria-label={`上移 ${name}`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => move(index, index + 1)}
                  disabled={index === selected.length - 1 || disabled}
                  aria-label={`下移 ${name}`}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => onChange(selected.filter((item) => item !== name))}
                  disabled={disabled}
                  aria-label={`移除 ${name}`}
                >
                  ×
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
