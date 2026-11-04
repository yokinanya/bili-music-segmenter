import { clipUrl, downloadUrl } from '@/lib/api';
import { isActive, type JobStatus } from '@/lib/types';
import { Icon } from './Icon';
import { ActionLink } from './Material';
import { MediaPlayer } from './MediaPlayer';
export function ClipList({ job, mediaId }: { job: JobStatus; mediaId: string }) {
  const clips = job.clips.filter((clip) => clip.media_id === mediaId);
  return <div className="results"><div className="section-head"><h3>片段 <span className="counter">{clips.length}</span></h3>
    {!isActive(job.state) && <ActionLink href={downloadUrl(job.id, 'archive')}><Icon name="download" />整批 ZIP</ActionLink>}</div>
    {clips.length === 0 && <div className="empty pane-empty"><Icon name="music" /><span>{isActive(job.state) ? '等待导出片段' : '暂无片段'}</span></div>}
    {clips.map((clip) => <article className="clip" key={clip.id}><MediaPlayer src={clipUrl(job.id, clip.id)} label={clip.title || clip.name} />
      <div className="section-head clip-heading"><div><h3>{clip.title || '未识别歌名'}</h3><p className="muted">{clip.artist || '未知歌手'} · {Math.round(clip.duration_seconds)} 秒</p></div><ActionLink href={clipUrl(job.id, clip.id, true)} download={clip.name} aria-label={`下载 ${clip.title || clip.name}`}><Icon name="download" />下载</ActionLink></div>
    </article>)}
  </div>;
}
