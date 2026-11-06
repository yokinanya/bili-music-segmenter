import { useEffect, useRef } from 'react';
import { Button } from './Material';
import { PAGE_ROWS, ROW_CHARACTERS, type LogBuffer, type LogRow } from './logBuffer';

function HighlightedRow({ row, match, length }: { row: LogRow; match: number; length: number }) {
  const start = Math.max(0, match - row.start);
  const end = Math.min(row.text.length, match + length - row.start);
  if (match < 0 || start >= end) return <>{row.text || '\u00a0'}</>;
  return <>{row.text.slice(0, start)}<mark>{row.text.slice(start, end)}</mark>{row.text.slice(end)}</>;
}
interface WindowProps {
  readonly buffer: LogBuffer;
  readonly page: number;
  readonly follow: boolean;
  readonly match: number;
  readonly keyword: string;
  readonly onPage: (page: number) => void;
  readonly onPause: () => void;
}
export function LogWindow({ buffer, page, follow, match, keyword, onPage, onPause }: WindowProps) {
  const box = useRef<HTMLDivElement>(null);
  const pages = Math.max(1, Math.ceil(buffer.rows.length / PAGE_ROWS));
  const current = Math.min(page, pages - 1);
  const first = current * PAGE_ROWS;
  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [buffer, follow]);
  useEffect(() => {
    const node = box.current;
    if (!node || follow) return;
    if (match >= 0) node.querySelector('mark')?.scrollIntoView({ block: 'nearest' });
    else node.scrollTop = 0;
  }, [current, match]);
  return <>
    <div className="log-pagination">
      <Button variant="text" disabled={!current} onClick={() => onPage(current - 1)}>上一页</Button>
      <label>历史页 <input aria-label="日志历史页" type="number" min={1} max={pages} value={current + 1}
        onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && value <= pages) onPage(value - 1); }} /> / {pages}</label>
      <Button variant="text" disabled={current >= pages - 1} onClick={() => onPage(current + 1)}>下一页</Button>
      <span>显示段 {first + 1}–{Math.min(first + PAGE_ROWS, buffer.rows.length)} / {buffer.rows.length}</span>
    </div>
    <div ref={box} className="log log-window" tabIndex={0} aria-label="执行日志（分页显示全部历史）"
      onWheel={event => { if (event.deltaY < 0) onPause(); }} onTouchStart={onPause}
      onKeyDown={event => { if (['ArrowUp', 'PageUp', 'Home'].includes(event.key)) onPause(); }}>
      {!buffer.length ? '等待进程输出…' : buffer.rows.slice(first, first + PAGE_ROWS).map((row, offset) =>
        <div className="log-row" key={first + offset}><HighlightedRow row={row} match={match} length={keyword.length} /></div>)}
    </div>
    <p className="log-status">保留全部历史；长行每 {ROW_CHARACTERS} 字符分段显示。查找覆盖全部已读取日志，区分大小写。</p>
  </>;
}
