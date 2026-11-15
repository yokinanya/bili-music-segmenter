'use client';
import { useEffect, useState } from 'react';
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
  mode: TaskDialogMode; onClose: () => void;
}

export function SongTasks({ project, selected, save, apply, mode, onClose }: Props) {
  const [options, setOptions] = useState<RunOptions | null>(null), [job, setJob] = useState<JobStatus | null>(null);
  const [task, setTask] = useState<ExportTask | null>(null), [candidates, setCandidates] = useState<SongClip[] | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [reuseCache, setReuseCache] = useState(true);
  const [applied, setApplied] = useState(false);
  const [loadingExports, setLoadingExports] = useState(false);
  const [filenameSuffix, setFilenameSuffix] = useState('');
  useEffect(() => { if (mode !== 'export') setFilenameSuffix(''); }, [mode, project.id]);
  const selection = project.clips.filter(clip => selected.includes(clip.id));
  const selectionKey = JSON.stringify(selection);
  useEffect(() => {
    if (mode !== 'export') return;
    let active = true;
    setLoadingExports(true);
    void editorApi.exports(project.id).then(({ tasks }) => {
      if (!active) return;
      const matching = tasks.filter(value => matchesExport(value, selection, filenameSuffix));
      setTask(matching.find(value => ['queued', 'running'].includes(value.state)) ?? matching.at(-1) ?? tasks.at(-1) ?? null);
    }).catch(cause => { if (active) setError(errorText(cause)); })
      .finally(() => { if (active) setLoadingExports(false); });
    return () => { active = false; };
  }, [mode, project.id, selectionKey, filenameSuffix]);
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
    setJob(await api.job(result.id)); setCandidates(null); setApplied(false);
  });
  const exporting = !!task && ['queued', 'running'].includes(task.state);
  const analyzing = !!job && ['queued', 'running'].includes(job.state);
  const completedSelection = !!task && task.state === 'succeeded' && matchesExport(task, selection, filenameSuffix);
  const running = job?.batch.flatMap(item => item.steps).filter(step => step.state === 'running').map(step => step.label) ?? [];
  const issues = [...new Set([job?.error, ...job?.batch.flatMap(item => [item.error, ...item.steps.filter(step => step.error).map(step => `${step.label}：${step.error}`)]) ?? []].filter(Boolean))];
  return <MaterialDialog open={mode !== null} title={mode === 'analysis' ? 'AI切片' : '导出选中歌曲'} onClose={onClose}>
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
        {job && !analyzing && <div className="analysis-result-actions">
          {!applied && <Button variant="outlined" disabled={busy} onClick={() => void run(async () => { setCandidates((await editorApi.candidates(project.id, job.id)).clips); })}>查看 AI 候选</Button>}
          {['failed', 'interrupted', 'cancelled'].includes(job.state) && <Button variant="outlined" disabled={busy} onClick={() => void run(async () => { await api.retry(job.id); setJob(await api.job(job.id)); })}>续跑分析</Button>}
        </div>}
        {candidates !== null && (candidates.length
          ? <div className="drawer-hint">{job?.state !== 'succeeded' ? '部分结果：' : ''}找到 {candidates.length} 个区间，添加不会覆盖手动片段。<Button onClick={() => { apply(candidates); setCandidates(null); setApplied(true); onClose(); }}>添加候选到时间轴</Button></div>
          : <p className="drawer-hint">本次没有可用的歌曲候选，仍可手动标记区间。</p>)}
        {applied && <p role="status">候选已添加到时间轴</p>}
      </section>}
      {mode === 'export' && <section className="drawer-group">
        <h3>已选 {selected.length} 个歌曲区间</h3>
        <TextField label="文件名后缀（可选）" value={filenameSuffix} disabled={busy || exporting} onChange={setFilenameSuffix} />
        <small className="drawer-hint">添加到扩展名前，仅用于本次导出；留空保留原文件名。</small>
        <div className="export-selection">{selection.map(clip => <div className="export-file-row" key={clip.id}><span>{exportFilename(clip.name, filenameSuffix)}</span></div>)}</div>
        {loadingExports && <p role="status">正在读取导出结果…</p>}
        {task && <div className="drawer-job" role="status">
          <span className={`drawer-tag ${task.state === 'succeeded' ? 'ok' : exporting ? 'run' : 'warn'}`}>{task.state === 'succeeded' ? '完成' : exporting ? '导出中' : task.state}</span>
          <span className="drawer-job-body"><small>草稿版本 {task.revision}{task.revision !== project.revision ? ' · 当前已更新' : ''}</small>
            <div className="export-progress-metric"><Progress label="导出歌曲进度" value={task.clips.length ? task.completed / task.clips.length : undefined} /><small>{task.completed} / {task.clips.length} 首</small></div>
            {task.progress && <div className="export-progress-metric"><Progress label="导出时长进度" value={task.progress.total_seconds ? task.progress.completed_seconds / task.progress.total_seconds : undefined} /><small>{task.progress.completed_seconds.toFixed(1)} / {task.progress.total_seconds.toFixed(1)} 秒</small></div>}
          </span>
        </div>}
        {task?.error && <p className="error">{task.error}</p>}
        {task && task.clips.some(clip => clip.path) && <div className="export-downloads">
          <h3>已生成文件 · {task.completed} / {task.clips.length}</h3>
          {task.state === 'succeeded' && <ActionLink variant="outlined" href={exportUrl(project.id, task.id, 'archive')}>下载整批 ZIP</ActionLink>}
          {task.clips.filter(clip => clip.path).map(clip => <div className="export-file-row" key={clip.id}><span>{clip.name}</span><ActionLink variant="text" href={exportUrl(project.id, task.id, `clip/${encodeURIComponent(clip.id)}`)}>下载</ActionLink></div>)}
        </div>}
        {(exporting || !completedSelection) && <div className="export-actions">
          {exporting && <Button variant="outlined" disabled={task?.cancel_requested} onClick={() => void run(async () => setTask(await editorApi.cancelExport(project.id, task!.id)))}>当前歌曲完成后停止</Button>}
          {!completedSelection && <Button disabled={busy || loadingExports || exporting || !selected.length}
            onClick={() => void run(async () => { const snapshot = await save(); setTask(await editorApi.export(snapshot, selected, filenameSuffix)); })}>
            导出选中区间 · {selected.length}
          </Button>}
        </div>}
      </section>}
      <div className="dialog-actions"><Button variant="text" onClick={onClose}>关闭</Button>
        {mode === 'analysis' && <Button variant="outlined" disabled={busy || (analyzing && job?.stop_requested) || (!analyzing && !options)} onClick={() => {
          if (analyzing) void run(async () => { await api.stop(job!.id); setJob(await api.job(job!.id)); });
          else void analyze();
        }}>{busy ? '正在提交…' : analyzing ? job?.stop_requested ? '正在停止…' : '停止分析' : job ? '重新分析' : '开始分析'}</Button>}
      </div>
    </div>
  </MaterialDialog>;
}
