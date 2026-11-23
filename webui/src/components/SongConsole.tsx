'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useSongEditor } from '@/lib/useSongEditor';
import { assetDropHandlers } from '@/lib/assetDrop';
import { mergeClips, type EditorProject, type SongClip } from '@/lib/editor';
import { sourceUrl } from '@/lib/editorApi';
import { previewType } from '@/lib/previewMedia';
import { mediaTime as clock, errorText } from '@/lib/format';
import { SongTimeline } from './SongTimeline';
import { SongProperties } from './SongProperties';
import { SongTasks, type TaskDialogMode } from './SongTasks';
import { PreviewTransport } from './PreviewTransport';
import { Button, MaterialDialog, Progress } from './Material';
import { Icon } from './Icon';
import { MergeClipsDialog } from './MergeClipsDialog';
import { previewSpaceAction } from '@/lib/previewSpace';
import { isInterruption } from '@/lib/playback';
import './song-console.css';

export function SongConsole({ toolbarTarget }: { toolbarTarget: HTMLElement | null }) {
  const editor = useSongEditor(), video = useRef<HTMLVideoElement>(null), [taskMode, setTaskMode] = useState<TaskDialogMode>(null);
  const [listJump, setListJump] = useState<{ projectId: string; time: number } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<EditorProject | null>(null);
  const [pendingMerge, setPendingMerge] = useState<SongClip[] | null>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const [draggingAssets, setDraggingAssets] = useState(false);
  const drop = assetDropHandlers({ busy: !!editor.busy, importFiles: editor.importFiles, highlight: setDraggingAssets });
  const registerVideo = useCallback((element: HTMLVideoElement | null) => { video.current = element; }, []);
  const clip = editor.history.present.find(value => value.id === editor.selected[0]);
  const seek = (value: number) => { if (video.current) video.current.currentTime = value; editor.seekTime(value); };
  const toggle = () => { if (!video.current) return; if (video.current.paused) void video.current.play().catch(cause => { if (!isInterruption(cause)) editor.setError(errorText(cause)); }); else video.current.pause(); };
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      const editing = event.composedPath().some(target => target instanceof HTMLElement && (
        ['INPUT', 'TEXTAREA', 'SELECT', 'MD-OUTLINED-TEXT-FIELD', 'MD-FILLED-TEXT-FIELD', 'MD-OUTLINED-SELECT'].includes(target.tagName)
        || target.isContentEditable || target.getAttribute('role') === 'textbox'));
      if (event.isComposing) return;
      if (event.code === 'Space') {
        if (previewSpaceAction({ editing, blocked: !!document.querySelector('md-dialog[open], dialog[open], [role="dialog"][aria-modal="true"]')
          || !!document.querySelector('.editor-view[hidden] .song-console:not([hidden])') }) === 'native') return;
        event.preventDefault(); event.stopImmediatePropagation();
        if (event.type === 'keydown' && !event.repeat) {
          const focused = document.activeElement;
          if (focused instanceof HTMLElement && focused.closest('.timeline-topbar')
            && focused.matches('button, [role="button"]')) focused.blur();
          toggle();
        }
        return;
      }
      if (event.type === 'keyup') return;
      if (event.defaultPrevented || event.altKey || editing) return;
      if (event.ctrlKey || event.metaKey) {
        if (event.key.toLowerCase() === 'z') { event.preventDefault(); editor.dispatch({ type: event.shiftKey ? 'redo' : 'undo' }); }
        return;
      }
      if (document.querySelector('md-dialog[open]')) return;
      if (event.key.toLowerCase() === 's' && !event.ctrlKey && !event.metaKey) editor.split();
      if (event.key === '[') { event.preventDefault(); editor.markIn(); }
      if (event.key === ']') { event.preventDefault(); editor.markOut(); }
      if (event.key === 'Enter' && !event.composedPath().some(target => target instanceof HTMLElement && target.tagName === 'BUTTON')
        && editor.marks.start !== null && editor.marks.end !== null && editor.marks.start < editor.marks.end) {
        event.preventDefault(); editor.add();
      }
      if (!clip) return;
      const key = event.key.toLowerCase();
      if (key === 'i' && editor.time < clip.end_seconds) editor.change(editor.history.present.map(c => c.id === clip.id ? { ...c, start_seconds: editor.time } : c));
      if (key === 'o' && editor.time > clip.start_seconds) editor.change(editor.history.present.map(c => c.id === clip.id ? { ...c, end_seconds: editor.time } : c));
    };
    window.addEventListener('keydown', keyboard, true);
    window.addEventListener('keyup', keyboard, true);
    return () => { window.removeEventListener('keydown', keyboard, true); window.removeEventListener('keyup', keyboard, true); };
  });
  const importInput = () => <input type="file" multiple accept="video/*,audio/*,.mkv,.flv,.ts" hidden disabled={!!editor.busy} onChange={e => { void editor.importFiles(Array.from(e.target.files ?? [])); e.target.value = ''; }} />;
  return <div className="song-console">
    {toolbarTarget && createPortal(<>
      <Button variant="text" disabled={!editor.project} onClick={() => setTaskMode('analysis')}>AI切片</Button>
      <Button variant="text" disabled={!editor.project || !editor.selected.length} onClick={() => setTaskMode('export')}>导出</Button>
    </>, toolbarTarget)}
    <div className="console-shell">
    <div className="console-body">
      <aside className={`asset-panel${draggingAssets ? ' asset-dragging' : ''}`} aria-label="素材库" {...drop}>
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
          {!editor.project && <label className="asset-drop empty">{importInput()}<strong>拖入文件或点击导入</strong><span>MP4 / MKV / FLV / TS</span></label>}
          {editor.projects.map(project => <div key={project.id} className="asset-row">
            <button className="asset-item" aria-pressed={project.id === editor.project?.id} onClick={() => editor.open(project)}>
              <span className="asset-thumb"><span /></span><span className="asset-copy"><strong>{project.name}</strong><small>{clock(project.duration)} · {project.clips.length} 首候选</small></span>
            </button>
            <button className="asset-remove" aria-label={`删除素材 ${project.name}`} disabled={!!editor.busy} onClick={() => setPendingDelete(project)}><Icon name="trash" size="sm" /></button>
          </div>)}
          {editor.project && <section className="asset-clips"><h3>歌曲区间 <span>{editor.history.present.length}</span></h3>
            {editor.history.present.map((value, index) => <button key={value.id} aria-pressed={editor.selected.includes(value.id)} onClick={event => {
              if (event.shiftKey) { editor.selectRange(value.id); return; }
              const multi = event.ctrlKey || event.metaKey;
              editor.select(value.id, multi);
              if (multi) return;
              const time = value.start_seconds;
              if (video.current) video.current.currentTime = time;
              editor.setTime(time);
              if (editor.project) setListJump({ projectId: editor.project.id, time });
            }}>
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
      <SongProperties clip={clip} onChange={value => editor.change(editor.history.present.map(c => c.id === value.id ? value : c))} />
    </div>
    {editor.project && <SongTasks key={editor.project.id} project={{ ...editor.project, clips: editor.history.present }} selected={editor.selected} save={editor.save} apply={clips => editor.change([...editor.history.present, ...clips])} mode={taskMode} onClose={() => setTaskMode(null)} onOpenExport={() => setTaskMode('export')} />}
    </div>
    <MaterialDialog open={!!pendingDelete} title="删除素材？" onClose={() => setPendingDelete(null)}>
      <p>将删除「{pendingDelete?.name}」及其歌曲区间草稿，磁盘上的源文件与已导出视频不受影响。此操作无法撤销。</p>
      <div className="dialog-actions"><Button onClick={() => setPendingDelete(null)}>取消</Button>
        <Button variant="filled" onClick={() => { const target = pendingDelete; setPendingDelete(null); if (target) void editor.remove(target); }}>确认删除</Button></div>
    </MaterialDialog>
    <MergeClipsDialog clips={pendingMerge} onClose={() => setPendingMerge(null)} onConfirm={() => {
      if (!pendingMerge || pendingMerge.length < 2) return;
      const ordered = [...pendingMerge].sort((a, b) => a.start_seconds - b.start_seconds);
      const merged = mergeClips(ordered);
      const ids = new Set(ordered.map(value => value.id));
      editor.change([...editor.history.present.filter(value => !ids.has(value.id)), merged]);
      editor.select(merged.id, false); setPendingMerge(null);
    }} />
    <section className="timeline-dock">
      {editor.error && <div className="error" role="alert">{editor.error}</div>}
      {editor.waveError && <div className="error" role="alert">波形生成失败：{editor.waveError}</div>}
      {editor.project && <SongTimeline key={editor.project.id} duration={editor.project.duration} time={editor.time} clips={editor.history.present} selected={editor.selected} waveform={editor.waveform}
        listJump={listJump?.projectId === editor.project.id ? listJump : null}
        canUndo={editor.history.past.length > 0} canRedo={editor.history.future.length > 0}
        marks={editor.marks} canSplit={editor.canSplit} onMarkIn={editor.markIn} onMarkOut={editor.markOut} onClearMarks={editor.clearMarks}
        onSeek={seek} onSelect={editor.select} onChange={editor.change}
        onLocate={value => { video.current?.pause(); if (video.current) video.current.currentTime = value; editor.locateBoundary(value); }}
        onMerge={ids => setPendingMerge(editor.history.present.filter(value => ids.includes(value.id)))}
        saving={!!editor.busy} onSave={() => void editor.run('正在保存…', async () => { await editor.save(); })}
        onAdd={editor.add} onSplit={editor.split} onDelete={ids => { editor.change(editor.history.present.filter(c => !ids.includes(c.id))); editor.setSelected(current => current.filter(id => !ids.includes(id))); }}
        onUndo={() => editor.dispatch({ type: 'undo' })} onRedo={() => editor.dispatch({ type: 'redo' })} />}
    </section>
  </div>;
}
