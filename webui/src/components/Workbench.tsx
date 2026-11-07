'use client';
import { useRef } from 'react';
import { api } from '@/lib/api';
import { validateParameters } from './Parameters';
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
  const inputPanel = useRef<HTMLElement>(null);
  const track = state.track;
  const mode = tab === '导入与设置' ? 'import' : tab === '日志与结果' ? 'output' : 'queue';
  return <div className='workspace-content'>
    <div className='compact-tabs'><Tabs value={tab} options={['导入与设置', '队列与进度', '日志与结果']} onChange={setTab} /></div>
    <div className={`workbench show-${mode}`}>
      <section ref={inputPanel} className='panel import-column' aria-label='导入与设置'>
        <Tabs label='导入方式' value={source} options={['本地文件', '视频链接']} onChange={setSource} />
        <div className='local-import input-scroll' hidden={source !== '本地文件'}>
          <ImportPanel draft={state.draft} busy={state.busy} />
          {state.options && <Parameters options={state.options} onChange={state.setOptions} />}
        </div>
        <div className='download-form-slot' hidden={source !== '视频链接'}>
          <DownloadPanel options={state.options} onStarted={track} url={state.downloadUrl} onUrlChange={state.setDownloadUrl}>
            {state.options && <Parameters options={state.options} onChange={state.setOptions} />}
          </DownloadPanel>
        </div>
        {source === '本地文件' && <div className='pane-footer'><Button variant='filled' disabled={state.busy || !state.options || !state.draft.files.length}
          onClick={() => { if (inputPanel.current && validateParameters(inputPanel.current)) void state.start(); }}>
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
    {job.can_complete_parts && <Button variant='filled' onClick={() => void state.action(() => api.retry(job.id))}>补齐分 P</Button>}
    {['failed', 'cancelled', 'interrupted'].includes(job.state) && <Button variant='filled' onClick={() => void state.action(() => api.retry(job.id))}>续跑</Button>}
    <Button disabled={job.batch.some((item) => item.can_reuse === false)} onClick={() => void state.action(() => state.rerun(job))}>{job.batch.some((item) => item.source_type === 'download') ? '复用视频重新分析' : '重新处理'}</Button>
    {job.batch.some((item) => item.source_url) && <Button onClick={() => void state.action(async () => state.redownload(job))}>重新下载原链接</Button>}
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
