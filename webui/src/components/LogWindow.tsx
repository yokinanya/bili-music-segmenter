import { useEffect, useRef } from 'react';
import { PAGE_ROWS, type LogBuffer, type LogRow } from './logBuffer';

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
  readonly complete: boolean;
  readonly onPause: () => void;
}
export function LogWindow({ buffer, page, follow, match, keyword, complete, onPause }: WindowProps) {
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
  return <div ref={box} className="log log-window" tabIndex={0} role="region" aria-label="执行日志"
      onWheel={event => { if (event.deltaY < 0) onPause(); }} onTouchStart={onPause}
      onKeyDown={event => { if (['ArrowUp', 'PageUp', 'Home'].includes(event.key)) onPause(); }}>
      {!buffer.length ? (complete ? '暂无日志' : '等待进程输出…') : buffer.rows.slice(first, first + PAGE_ROWS).map((row, offset) =>
        <div className="log-row" key={first + offset}><HighlightedRow row={row} match={match} length={keyword.length} /></div>)}
  </div>;
}
