'use client';
import { useMemo, useState } from 'react';
import { Button } from './Material';
import { LogActions } from './LogActions';
import { LogWindow } from './LogWindow';
import { findLog, PAGE_ROWS, rowAt } from './logBuffer';
import { useLogStream } from './useLogStream';
import './log-viewer.css';

export function LogViewer(props: { jobId: string; index: number }) {
  return <LogSession key={`${props.jobId}:${props.index}`} {...props} />;
}
function LogSession({ jobId, index }: { jobId: string; index: number }) {
  const { buffer, error, complete, retry } = useLogStream(jobId, index);
  const [follow, setFollow] = useState(true);
  const [page, setPage] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [selection, setSelection] = useState(-1);
  const matches = useMemo(() => findLog(buffer, keyword), [buffer, keyword]);
  const selected = selection >= 0 && matches.length ? Math.min(selection, matches.length - 1) : -1;
  const match = selected < 0 ? -1 : matches[selected];
  const currentPage = follow ? Math.floor((buffer.rows.length - 1) / PAGE_ROWS) : page;
  const changePage = (value: number) => { setFollow(false); setSelection(-1); setPage(value); };
  const navigate = (direction: number) => {
    if (!matches.length) return;
    const next = selected < 0 ? (direction > 0 ? 0 : matches.length - 1) : (selected + direction + matches.length) % matches.length;
    setSelection(next); setFollow(false);
    setPage(Math.floor(rowAt(buffer.rows, matches[next]) / PAGE_ROWS));
  };
  return <div className="log-wrap">
    <div className="section-head"><h3>执行日志</h3>
      <Button variant="text" onClick={() => { setPage(currentPage); setFollow(!follow); setSelection(-1); }}>{follow ? '暂停跟随' : '跟随最新'}</Button>
    </div>
    <div className="log-search">
      <label>查找日志 <input type="search" value={keyword} placeholder="输入关键词"
        onChange={event => { setKeyword(event.target.value); setSelection(-1); }}
        onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); navigate(event.shiftKey ? -1 : 1); } }} /></label>
      <Button variant="text" disabled={!matches.length} onClick={() => navigate(-1)}>上一个</Button>
      <Button variant="text" disabled={!matches.length} onClick={() => navigate(1)}>下一个</Button>
      <span role="status">{selected + 1} / {matches.length} 个匹配</span>
    </div>
    <LogActions jobId={jobId} index={index} />
    {error && <div className="error" role="alert">读取日志失败：{error}<Button onClick={retry}>重新读取日志</Button></div>}
    <span className="log-status">{complete ? '日志已读取完毕' : error ? '读取已停止' : '持续读取日志中…'} · {follow ? '跟随最新' : '已暂停跟随，仍在读取'}</span>
    <LogWindow buffer={buffer} page={currentPage} follow={follow} match={match} keyword={keyword}
      onPage={changePage} onPause={() => { setPage(currentPage); setFollow(false); }} />
  </div>;
}
