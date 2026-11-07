'use client';
import { useId, useState } from 'react';
import { Button } from './Material';
import { LogTools } from './LogTools';
import { LogWindow } from './LogWindow';
import { useLogNavigation } from './useLogNavigation';
import { useLogStream } from './useLogStream';
import './log-viewer.css';

export function LogViewer(props: { jobId: string; index: number }) {
  return <LogSession key={`${props.jobId}:${props.index}`} {...props} />;
}
function LogSession({ jobId, index }: { jobId: string; index: number }) {
  const { buffer, error, complete, retry } = useLogStream(jobId, index);
  const navigation = useLogNavigation(buffer);
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsId = useId();
  return <div className="log-wrap">
    <div className="section-head log-heading"><h3>执行日志</h3>
      <div className="log-actions">
        <Button variant="text" aria-pressed={navigation.follow} onClick={navigation.toggleFollow}>
          {navigation.follow ? '暂停跟随' : '跟随最新'}
        </Button>
        <Button variant="text" aria-expanded={toolsOpen} aria-controls={toolsId}
          onClick={() => setToolsOpen(value => !value)}>工具</Button>
      </div>
    </div>
    <div id={toolsId} className="log-tools" hidden={!toolsOpen}>
      <LogTools jobId={jobId} index={index} navigation={navigation} />
    </div>
    {error && <div className="error" role="alert">读取日志失败：{error}<Button onClick={retry}>重新读取日志</Button></div>}
    <LogWindow buffer={buffer} page={navigation.currentPage} follow={navigation.follow}
      match={navigation.match} keyword={navigation.keyword} complete={complete} onPause={navigation.pause} />
  </div>;
}
