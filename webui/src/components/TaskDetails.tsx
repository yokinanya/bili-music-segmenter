import type { JobStatus } from '@/lib/types';
import { Disclosure } from './Disclosure';

const timestamp = (value: string | null) => value ? new Date(value).toLocaleString() : '尚未结束';

export function TaskDetails({ job }: { job: JobStatus }) {
  return <Disclosure title="任务详情" className="task-details">
    <dl className="task-metadata"><dt>任务 ID</dt><dd><code>{job.id}</code></dd>
      <dt>执行次数</dt><dd>第 {job.attempt} 次</dd>
      <dt>创建时间</dt><dd>{timestamp(job.started_at)}</dd>
      <dt>结束时间</dt><dd>{timestamp(job.finished_at)}</dd>
    </dl>
    <h3>来源与文件</h3><ul className="task-sources">{job.batch.map((item) => <li key={item.id}>
      <strong>{item.media}</strong><span className="muted"> · {item.source_type === 'download' ? '在线下载' : item.source_type === 'upload' ? '本地上传' : '来源未记录'}</span>
      {item.source_url && <p className="source-url">{item.source_url}</p>}
    </li>)}</ul>
    <h3>处理参数</h3><dl className="task-options">{Object.entries(job.options).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{typeof value === 'boolean' ? value ? '启用' : '关闭' : value}</dd></div>)}</dl>
  </Disclosure>;
}
