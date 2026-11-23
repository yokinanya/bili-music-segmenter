'use client';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { editorApi, exportUrl, type ExportTask } from '@/lib/editorApi';
import type { EditorProject, SongClip } from '@/lib/editor';
import type { JobStatus, RunOptions } from '@/lib/types';
import { errorText } from '@/lib/format';
import { ActionLink, Button, MaterialDialog, Progress, Switch, TextField } from './Material';
import { exportFilename, matchesExport } from '@/lib/exportSnapshot';
import { AnalysisProgress } from './AnalysisProgress';

export type TaskDialogMode = 'analysis' | 'export' | null;

interface Props {
  project: EditorProject; selected: string[]; save: () => Promise<EditorProject>; apply: (clips: SongClip[]) => void;
  mode: TaskDialogMode; onClose: () => void; onOpenExport: () => void;
}

export function SongTasks({ project, selected, save, apply, mode, onClose, onOpenExport }: Props) {
  const [options, setOptions] = useState<RunOptions | null>(null), [job, setJob] = useState<JobStatus | null>(null);
  const [task, setTask] = useState<ExportTask | null>(null), [noCandidates, setNoCandidates] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [reuseCache, setReuseCache] = useState(true);
  const [applied, setApplied] = useState(false);
  const [loadingExports, setLoadingExports] = useState(false);
  const [filenameSuffix, setFilenameSuffix] = useState('');
  const restored = useRef(false);
  const selection = project.clips.filter(clip => selected.includes(clip.id));
  const selectionKey = JSON.stringify(selection);
  const restoreExports = useEffectEvent((tasks: ExportTask[]) => {
    const matching = tasks.filter(value => matchesExport(value, selection, filenameSuffix));
    const running = tasks.find(value => ['queued', 'running'].includes(value.state));
    const latest = running ?? matching.at(-1) ?? tasks.at(-1) ?? null;
    setTask(current => running ?? tasks.find(value => value.id === current?.id) ?? latest);
    if (!restored.current) {
      restored.current = true;
      if (latest) setFilenameSuffix(latest.filename_suffix ?? '');
    }
  });
  useEffect(() => {
    let active = true;
    setLoadingExports(true);
    void editorApi.exports(project.id).then(({ tasks }) => {
      if (active) restoreExports(tasks);
    }).catch(cause => { if (active) setError(errorText(cause)); })
      .finally(() => { if (active) setLoadingExports(false); });
    return () => { active = false; };
  }, [mode, project.id, selectionKey]);
  useEffect(() => { if (mode === 'analysis') void api.bootstrap().then(data => setOptions(data.defaults)).catch(cause => setError(errorText(cause))); }, [mode]);
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.state)) return;
    const timer = setTimeout(() => { void api.job(job.id).then(setJob).catch(cause => setError(errorText(cause))); }, 1000);
    return () => clearTimeout(timer);
  }, [job]);
  useEffect(() => {
    if (!task || !['queued', 'running'].includes(task.state)) return;
    const timer = setTimeout(() => { void editorApi.exportStatus(project.id, task.id).then(setTask).catch(cause => setError(errorText(cause))); }, 1000);
    return () => clearTimeout(timer);
  }, [task, project.id]);
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await work(); } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  const analyze = () => run(async () => {
    if (!options) throw new Error('分析参数尚未加载');
    await save();
    const result = await editorApi.analyze(project.id, options, !reuseCache);
    setJob(await api.job(result.id)); setNoCandidates(false); setApplied(false);
  });
  const addToTimeline = (jobId: string) => run(async () => {
    const { clips } = await editorApi.candidates(project.id, jobId);
    if (!clips.length) { setNoCandidates(true); return; }
    apply(clips);
    setApplied(true);
    onClose();
  });
  const exporting = !!task && ['queued', 'running'].includes(task.state);
  const analyzing = !!job && ['queued', 'running'].includes(job.state);
  const canAdd = !!job && !analyzing && !applied && !noCandidates;
  const completedSelection = !!task && task.state === 'succeeded' && matchesExport(task, selection, filenameSuffix);
  const running = job?.batch.flatMap(item => item.steps).filter(step => step.state === 'running').map(step => step.label) ?? [];
  const issues = [...new Set([job?.error, ...job?.batch.flatMap(item => [item.error, ...item.steps.filter(step => step.error).map(step => `${step.label}：${step.error}`)]) ?? []].filter(Boolean))];
  const exportState = task?.cancel_requested && exporting ? '等待停止' : task?.state === 'queued' ? '等待导出'
    : exporting ? '正在导出' : task?.state === 'succeeded' ? '导出完成' : task?.state === 'cancelled' ? '导出已停止'
    : task?.state === 'interrupted' ? '导出已中断' : '导出失败';
  return <>
    {mode === null && task && <div className="minimized-export">
      <Button variant="text" onClick={onOpenExport}>{exportState} · 查看任务</Button>
      {exporting && <Progress label="后台导出进度" value={task.clips.length ? task.completed / task.clips.length : undefined} />}
      {error && <span className="error" role="alert">{error}</span>}
    </div>}
    <MaterialDialog open={mode !== null} title={mode === 'analysis' ? 'AI切片' : '导出选中歌曲'} onClose={onClose}>
    <div className="song-task-dialog">
      {error && <div className="error" role="alert">{error}</div>}
      {mode === 'analysis' && <section className="drawer-group">
        <h3>{project.name}</h3>
        {job && <div className="drawer-job" role="status">
          <span className={`drawer-tag ${analyzing ? 'run' : job.state === 'succeeded' ? 'ok' : 'warn'}`}>{analyzing ? '分析中' : job.state === 'succeeded' ? '已完成' : job.state === 'failed' ? '分析失败' : job.state}</span>
          <span className="drawer-job-body"><b>{running[0] ?? (analyzing ? '准备中' : job.state === 'succeeded' ? '分析完成' : '任务未完整完成，部分结果可能可用')}</b><small>gemini-3.8-flash · high</small></span>
        </div>}
        {issues.map(issue => <p className="error" role="alert" key={issue}>{issue}</p>)}
        <div className="drawer-row"><span>模型</span><code>gemini-3.8-flash · high</code></div>
        <Switch label="复用识别缓存" checked={reuseCache} disabled={busy || analyzing} onChange={setReuseCache} />
        <small className="drawer-hint">相同音频和参数复用已有结果；取消勾选可重新识别。</small>
        {analyzing && mode === 'analysis' && <AnalysisProgress job={job!} />}
        {job && ['failed', 'interrupted', 'cancelled'].includes(job.state) && <Button variant="outlined" disabled={busy} onClick={() => void run(async () => {
          await api.retry(job.id);
          setJob(await api.job(job.id));
          setNoCandidates(false);
        })}>续跑分析</Button>}
        {noCandidates && <p className="drawer-hint" role="status">本次没有可用的歌曲候选，仍可手动标记区间。</p>}
        {applied && <p role="status">候选已添加到时间轴</p>}
      </section>}
      {mode === 'export' && <section className="drawer-group">
        <h3>已选 {selected.length} 个歌曲区间</h3>
        <TextField label="文件名后缀（可选）" value={filenameSuffix} disabled={busy || exporting} onChange={value => { restored.current = true; setFilenameSuffix(value); }} />
        <small className="drawer-hint">添加到扩展名前，仅用于本次导出；留空保留原文件名。</small>
        <details className="export-file-details" key={mode + project.id}>
          <summary>查看文件列表 · {selection.length} 首</summary>
          <div className="export-selection">{selection.map(clip => <div className="export-file-row" key={clip.id}><span>{exportFilename(clip.name, filenameSuffix)}</span></div>)}</div>
        </details>
        {loadingExports && <p role="status">正在读取导出结果…</p>}
        {task && <div className="drawer-job" role="status">
          <span className={`drawer-tag ${task.state === 'succeeded' ? 'ok' : exporting ? 'run' : 'warn'}`}>{exportState}</span>
          <span className="drawer-job-body"><small>草稿版本 {task.revision}{task.revision !== project.revision ? ' · 当前已更新' : ''}</small>
            <div className="export-progress-metric"><Progress label="导出歌曲进度" value={task.clips.length ? task.completed / task.clips.length : undefined} /><small>{task.completed} / {task.clips.length} 首</small></div>
            {task.progress && <div className="export-progress-metric"><Progress label="导出时长进度" value={task.progress.total_seconds ? task.progress.completed_seconds / task.progress.total_seconds : undefined} /><small>{task.progress.completed_seconds.toFixed(1)} / {task.progress.total_seconds.toFixed(1)} 秒</small></div>}
          </span>
        </div>}
        {task?.error && <p className="error">{task.error}</p>}
        {task && task.clips.some(clip => clip.path) && <div className="export-downloads">
          <h3>已生成文件 · {task.completed} / {task.clips.length}</h3>
          {task.state === 'succeeded' && <ActionLink variant="outlined" href={exportUrl(project.id, task.id, 'archive')}>下载整批 ZIP</ActionLink>}
          <details className="export-file-details" key={task.id}>
            <summary>查看文件／单独下载</summary>
            <div className="export-selection">{task.clips.filter(clip => clip.path).map(clip => <div className="export-file-row" key={clip.id}><span>{clip.name}</span><ActionLink variant="text" href={exportUrl(project.id, task.id, `clip/${encodeURIComponent(clip.id)}`)}>下载</ActionLink></div>)}</div>
          </details>
        </div>}
        {(exporting || !completedSelection) && <div className="export-actions">
          <Button variant={exporting ? 'outlined' : 'filled'}
            disabled={busy || loadingExports || (exporting ? !!task.cancel_requested : !selected.length)}
            title={exporting ? '完成当前歌曲后停止，已完成文件会保留' : '导出当前选择的歌曲'}
            onClick={() => void run(async () => {
              if (exporting) { setTask(await editorApi.cancelExport(project.id, task.id)); return; }
              const snapshot = await save(); setTask(await editorApi.export(snapshot, selected, filenameSuffix));
            })}>
            {busy ? exporting ? '正在请求停止…' : '正在开始导出…'
              : loadingExports ? '读取中…' : exporting ? task.cancel_requested ? '等待停止' : '停止导出'
              : `开始导出 ${selected.length} 首歌曲`}
          </Button>
          {exporting && <small className="export-action-hint">{task.cancel_requested ? '当前歌曲完成后结束，已完成文件会保留。' : '停止会在当前歌曲完成后生效。'}收起窗口不影响导出。</small>}
        </div>}
      </section>}
      <div className="dialog-actions"><Button variant="text" onClick={onClose}>{mode === 'export' && exporting ? '收起窗口' : '关闭'}</Button>
        {mode === 'analysis' && <Button variant="outlined" disabled={busy || (analyzing && job?.stop_requested) || (!analyzing && !options)} onClick={() => {
          if (analyzing) void run(async () => { await api.stop(job!.id); setJob(await api.job(job!.id)); });
          else void analyze();
        }}>{busy && !canAdd ? '正在提交…' : analyzing ? job?.stop_requested ? '正在停止…' : '停止分析' : job ? '重新分析' : '开始分析'}</Button>}
        {mode === 'analysis' && canAdd && <Button variant="filled" disabled={busy} onClick={() => addToTimeline(job.id)}>
          {job.state === 'succeeded' ? '添加到时间轴' : '添加部分结果'}
        </Button>}
      </div>
    </div>
  </MaterialDialog></>;
}
