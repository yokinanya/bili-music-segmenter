'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useSongEditor } from '@/lib/useSongEditor';
import type { EditorProject } from '@/lib/editor';
import { sourceUrl } from '@/lib/editorApi';
import { previewType } from '@/lib/previewMedia';
import { mediaTime as clock, errorText } from '@/lib/format';
import { SongTimeline } from './SongTimeline';
import { SongProperties } from './SongProperties';
import { SongTasks, type TaskDialogMode } from './SongTasks';
import { PreviewTransport } from './PreviewTransport';
import { Button, MaterialDialog, Progress } from './Material';
import { Icon } from './Icon';
import { previewSpaceAction } from '@/lib/previewSpace';
import { isInterruption } from '@/lib/playback';
import './song-console.css';

export function SongConsole({ toolbarTarget }: { toolbarTarget: HTMLElement | null }) {
  const editor = useSongEditor(), video = useRef<HTMLVideoElement>(null), [taskMode, setTaskMode] = useState<TaskDialogMode>(null);
  const [pendingDelete, setPendingDelete] = useState<EditorProject | null>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const registerVideo = useCallback((element: HTMLVideoElement | null) => { video.current = element; }, []);
  const clip = editor.history.present.find(value => value.id === editor.selected[0]);
  const seek = (value: number) => { if (video.current) video.current.currentTime = value; editor.seekTime(value); };
  const toggle = () => { if (!video.current) return; if (video.current.paused) void video.current.play().catch(cause => { if (!isInterruption(cause)) editor.setError(errorText(cause)); }); else video.current.pause(); };
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey || event.composedPath().some(target => target instanceof HTMLElement && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable))) return;
      if (event.ctrlKey || event.metaKey) {
        if (event.key.toLowerCase() === 'z') { event.preventDefault(); editor.dispatch({ type: event.shiftKey ? 'redo' : 'undo' }); }
        return;
      }
      if (event.code === 'Space') {
        const path = event.composedPath().filter((target): target is HTMLElement => target instanceof HTMLElement);
        if (previewSpaceAction({ editing: false, button: path.some(target => target.tagName === 'BUTTON'),
          adjustment: path.some(target => target.classList.contains('boundary-nudge')),
          blocked: !!document.querySelector('md-dialog[open]') || !!document.querySelector('.editor-view[hidden] .song-console:not([hidden])') }) === 'native') return;
        event.preventDefault();
        if (!event.repeat) toggle();
      }
      if (event.key.toLowerCase() === 's' && !event.ctrlKey && !event.metaKey) editor.split();
      if (!clip) return;
      const key = event.key.toLowerCase();
      if (key === 'i' && editor.time < clip.end_seconds) editor.change(editor.history.present.map(c => c.id === clip.id ? { ...c, start_seconds: editor.time } : c));
      if (key === 'o' && editor.time > clip.start_seconds) editor.change(editor.history.present.map(c => c.id === clip.id ? { ...c, end_seconds: editor.time } : c));
    };
    window.addEventListener('keydown', keyboard, true); return () => window.removeEventListener('keydown', keyboard, true);
  });
  const dirty = !!editor.project && JSON.stringify(editor.project.clips) !== JSON.stringify(editor.history.present);
  const importInput = () => <input type="file" multiple accept="video/*,audio/*,.mkv,.flv,.ts" hidden disabled={!!editor.busy} onChange={e => { void editor.importFiles(Array.from(e.target.files ?? [])); e.target.value = ''; }} />;
  return <div className="song-console">
    {toolbarTarget && createPortal(<>
      <Button variant="text" disabled={!editor.project} onClick={() => setTaskMode('analysis')}>AI切片</Button>
      <Button variant="text" disabled={!editor.project || !editor.selected.length} onClick={() => setTaskMode('export')}>导出</Button>
    </>, toolbarTarget)}
    <div className="console-shell">
    <div className="console-body">
      <aside className="asset-panel" aria-label="素材库">
        <header><h2>素材</h2><Button variant="text" onClick={() => importRef.current?.click()} disabled={!!editor.busy}>导入录像</Button><input ref={importRef} type="file" multiple accept="video/*,audio/*,.mkv,.flv,.ts" hidden onChange={event => { void editor.importFiles(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ''; }} /></header>
        <div className="asset-scroll">
          {editor.importProgress && <div className="operation-progress import-progress" role="status">
            <strong>导入 {editor.importProgress.index} / {editor.importProgress.count} · {editor.importProgress.name}</strong>
            <Progress label="录像上传进度" value={editor.importProgress.stage === 'uploading' ? editor.importProgress.sent / editor.importProgress.size : undefined} />
            <small>{editor.importProgress.stage === 'registering' ? '正在登记文件…'
              : editor.importProgress.stage === 'probing' ? '上传完成，正在读取媒体信息…'
              : editor.importProgress.sent >= editor.importProgress.size ? '文件已发送，等待服务端写入与校验完成…'
              : `${(editor.importProgress.sent / 1024 ** 2).toFixed(1)} / ${(editor.importProgress.size / 1024 ** 2).toFixed(1)} MiB · ${(editor.importProgress.sent / editor.importProgress.size * 100).toFixed(1)}%`}</small>
          </div>}
          {!editor.project && <label className="asset-drop empty">{importInput()}<strong>点击导入录像</strong><span>MP4 / MKV / FLV / TS</span></label>}
          {editor.projects.map(project => <div key={project.id} className="asset-row">
            <button className="asset-item" aria-pressed={project.id === editor.project?.id} onClick={() => editor.open(project)}>
              <span className="asset-thumb"><span /></span><span className="asset-copy"><strong>{project.name}</strong><small>{clock(project.duration)} · {project.clips.length} 首候选</small></span>
            </button>
            <button className="asset-remove" aria-label={`删除素材 ${project.name}`} disabled={!!editor.busy} onClick={() => setPendingDelete(project)}><Icon name="trash" size="sm" /></button>
          </div>)}
          {editor.project && <section className="asset-clips"><h3>歌曲区间 <span>{editor.history.present.length}</span></h3>
            {editor.history.present.map((value, index) => <button key={value.id} aria-pressed={editor.selected.includes(value.id)} onClick={e => { if (e.shiftKey) { editor.selectRange(value.id); return; } editor.select(value.id, e.ctrlKey || e.metaKey); if (!e.ctrlKey && !e.metaKey) { if (video.current) video.current.currentTime = value.start_seconds; editor.setTime(value.start_seconds); } }}>
              <span className="clip-index">{String(index + 1).padStart(2, '0')}</span><span><strong>{value.title || '待命名歌曲'}</strong><small>{clock(value.start_seconds)} — {clock(value.end_seconds)}</small></span>
            </button>)}</section>}
        </div>
      </aside>
      <section className="preview-panel" aria-label="原视频预览">
        <PreviewTransport key={editor.project?.id ?? 'empty'} src={editor.project ? sourceUrl(editor.project.id) : null}
          type={previewType(editor.project?.name ?? '')} duration={editor.project?.duration}
          stopAt={clip?.end_seconds}
          onTime={editor.setTime} onSeek={editor.seekTime} onError={editor.setError} registerVideo={registerVideo} />
      </section>
      <SongProperties clip={clip} duration={editor.project?.duration ?? 0} onChange={value => editor.change(editor.history.present.map(c => c.id === value.id ? value : c))}
        onLocate={value => { video.current?.pause(); if (video.current) video.current.currentTime = value; editor.locateBoundary(value); }} />
    </div>
    {editor.project && <SongTasks key={editor.project.id} project={{ ...editor.project, clips: editor.history.present }} selected={editor.selected} save={editor.save} apply={clips => editor.change([...editor.history.present, ...clips])} mode={taskMode} onClose={() => setTaskMode(null)} />}
    </div>
    <MaterialDialog open={!!pendingDelete} title="删除素材？" onClose={() => setPendingDelete(null)}>
      <p>将删除「{pendingDelete?.name}」及其歌曲区间草稿，磁盘上的源文件与已导出视频不受影响。此操作无法撤销。</p>
      <div className="dialog-actions"><Button onClick={() => setPendingDelete(null)}>取消</Button>
        <Button variant="filled" onClick={() => { const target = pendingDelete; setPendingDelete(null); if (target) void editor.remove(target); }}>确认删除</Button></div>
    </MaterialDialog>
    <section className="timeline-dock">
      {editor.error && <div className="error" role="alert">{editor.error}</div>}
      {editor.waveError && <div className="error" role="alert">波形生成失败：{editor.waveError}</div>}
      {editor.project && <SongTimeline duration={editor.project.duration} time={editor.time} clips={editor.history.present} selected={editor.selected} waveform={editor.waveform}
        canUndo={editor.history.past.length > 0} canRedo={editor.history.future.length > 0}
        onSeek={seek} onSelect={editor.select} onChange={editor.change}
        onAdd={editor.add} onSplit={editor.split} onDelete={() => editor.change(editor.history.present.filter(c => !editor.selected.includes(c.id)))}
        onUndo={() => editor.dispatch({ type: 'undo' })} onRedo={() => editor.dispatch({ type: 'redo' })} />}
      <footer className="editor-status"><span role="status">{editor.busy || editor.notice || (dirty ? '有未保存修改' : editor.project ? '草稿已保存' : '')}</span>
        <span className="status-hint">入点 <kbd>I</kbd> 出点 <kbd>O</kbd> 拆分 <kbd>S</kbd></span>
        {editor.history.present.length > 0 && <span className="status-count">已选 <b>{editor.selected.length}</b> / {editor.history.present.length}</span>}
        <Button variant="text" disabled={editor.selected.length < 2} title="取选中区间的外包范围，包含中间间隔" onClick={editor.merge}>合并（含间隔）</Button>
        <Button variant="text" disabled={!editor.project || !!editor.busy} onClick={() => void editor.run('正在保存…', async () => { await editor.save(); })}>保存草稿</Button>
      </footer>
    </section>
  </div>;
}
