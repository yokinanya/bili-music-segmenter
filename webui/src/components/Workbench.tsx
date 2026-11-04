'use client';
import { api } from '@/lib/api';
import { isActive } from '@/lib/types';
import type { useWorkspace } from '@/lib/useWorkspace';
import { Button, Tabs } from './Material';
import { Icon } from './Icon';
import { ImportPanel } from './ImportPanel';
import { Parameters } from './Parameters';
import { DownloadPanel } from './DownloadPanel';
import { JobView } from './JobView';

type WorkspaceState = ReturnType<typeof useWorkspace>;
export function Workbench({ state }: { state: WorkspaceState }) {
  const { view: tab, setView: setTab, source, setSource } = state;
  const track = (id: string) => { state.track(id); setTab('队列与进度'); };
  const mode = tab === '导入与设置' ? 'import' : tab === '日志与结果' ? 'output' : 'queue';
  return <div className='workspace-content'>
    <div className='compact-tabs'><Tabs value={tab} options={['导入与设置', '队列与进度', '日志与结果']} onChange={setTab} /></div>
    <div className={`workbench show-${mode}`}>
      <section className='panel import-column' aria-label='导入与设置'>
        <Tabs label='导入方式' value={source} options={['本地文件', '视频链接']} onChange={setSource} />
        <div className='input-scroll'>
          <div hidden={source !== '本地文件'}><ImportPanel draft={state.draft} busy={state.busy} /></div>
          <div hidden={source !== '视频链接'}><DownloadPanel options={state.options} onStarted={track} /></div>
          {state.options && <Parameters options={state.options} onChange={state.setOptions} />}
        </div>
        {source === '本地文件' && <div className='pane-footer'><Button variant='filled' disabled={state.busy || !state.options || !state.draft.files.length}
          onClick={() => void state.start().then((id) => { if (id) setTab('队列与进度'); })}>
          <Icon name='play' />{state.busy ? '正在上传…' : `开始处理${state.draft.files.length ? ` · ${state.draft.files.length}` : ''}`}
        </Button></div>}
      </section>
      <div className='task-tabs'><Tabs value={tab === '日志与结果' ? tab : '队列与进度'} options={['队列与进度', '日志与结果']} onChange={setTab} /></div>
      {state.current.job ? <JobView key={state.current.job.id} job={state.current.job} error={state.current.error}
        onRetry={state.current.retry} actions={<TaskActions state={state} />} /> : <EmptyTask error={state.current.error} retry={state.current.retry} />}
    </div>
  </div>;
}
function TaskActions({ state }: { state: WorkspaceState }) {
  const job = state.current.job!;
  if (isActive(job.state)) return <Button variant='outlined' onClick={() => void state.action(() => api.stop(job.id))}><Icon name='stop' />停止任务</Button>;
  return <>
    {['failed', 'cancelled', 'interrupted'].includes(job.state) && <Button variant='filled' onClick={() => void state.action(() => api.retry(job.id))}>续跑</Button>}
    <Button onClick={() => void state.action(() => state.rerun(job))}>重新处理</Button>
  </>;
}
function EmptyTask({ error, retry }: { error: string; retry: () => void }) {
  return <>
    <section className='panel task-main'><div className='pane-heading'><h2>处理队列</h2></div>
      {error ? <div className='error' role='alert'>{error}<Button onClick={retry}>重新读取</Button></div> : <div className='empty pane-empty'><Icon name='work' /><span>暂无任务</span></div>}
    </section>
    <section className='panel output-panel'><div className='pane-heading'><h2>日志与结果</h2></div><div className='empty pane-empty'><Icon name='music' /><span>暂无结果</span></div></section>
  </>;
}
