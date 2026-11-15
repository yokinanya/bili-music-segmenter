'use client';
import { api } from '@/lib/api';
import { isActive } from '@/lib/types';
import type { useWorkspace } from '@/lib/useWorkspace';
import { Button, Tabs } from './Material';
import { Icon } from './Icon';
import { DownloadPanel } from './DownloadPanel';
import { JobView } from './JobView';

type WorkspaceState = ReturnType<typeof useWorkspace>;
export function Workbench({ state }: { state: WorkspaceState }) {
  const { view: tab, setView: setTab } = state;
  const layout = tab === '导入与设置' ? 'import' : tab === '日志与结果' ? 'output' : 'queue';
  return <div className='workspace-content'>
    <div className='compact-tabs'><Tabs value={tab} options={['导入与设置', '队列与进度', '日志与结果']} onChange={setTab} /></div>
    <div className={`workbench show-${layout}`}>
      <section className='panel import-column' aria-label='导入与设置'>
        <DownloadPanel options={state.options} onStarted={state.track} url={state.downloadUrl} onUrlChange={state.setDownloadUrl}>
        </DownloadPanel>
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
    {job.can_complete_parts && <Button variant='filled' onClick={() => void state.action(() => api.retry(job.id))}>补齐分 P</Button>}
    {['failed', 'cancelled', 'interrupted'].includes(job.state) && <Button variant='filled' onClick={() => void state.action(() => api.retry(job.id))}>续跑</Button>}
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
