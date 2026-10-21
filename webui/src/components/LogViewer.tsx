'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

interface Props {
  text: string;
  /** Whether the producer is still writing; controls the "follow" hint. */
  streaming: boolean;
  title: string;
}

const ERROR_LINE = /\b(ERROR|CRITICAL)\b|Traceback|Error:|错误/;

/** Renders incrementally: only the new tail is parsed, so long logs stay responsive. */
export function LogViewer({ text, streaming, title }: Props) {
  const [follow, setFollow] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const boxRef = useRef<HTMLPreElement>(null);
  const rendered = useRef(0);
  const [lines, setLines] = useState<{ text: string; error: boolean }[]>([]);

  useEffect(() => {
    if (text.length < rendered.current) {
      // The log was replaced (new job or a reset): rebuild instead of appending a stale tail.
      rendered.current = 0;
      setLines([]);
    }
    if (text.length === rendered.current) return;
    const tail = text.slice(rendered.current);
    rendered.current = text.length;
    const parts = tail.split('\n');
    // The last part may still be an unfinished line; keep it until the next chunk completes it.
    const complete = parts.slice(0, -1);
    setLines((previous) => [
      ...previous,
      ...complete.map((line) => ({ text: line, error: ERROR_LINE.test(line) })),
    ]);
  }, [text]);

  const body = useMemo(() => lines, [lines]);

  useEffect(() => {
    if (!autoScroll) return;
    const box = boxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [body, autoScroll]);

  const onScroll = () => {
    const box = boxRef.current;
    if (!box) return;
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 24;
    setAutoScroll(atBottom);
    setFollow(atBottom);
  };

  const jumpToEnd = () => {
    const box = boxRef.current;
    if (!box) return;
    box.scrollTop = box.scrollHeight;
    setAutoScroll(true);
    setFollow(true);
  };

  return (
    <div className="log-wrap">
      <div className="log-head">
        <span className="muted small">{title}</span>
        <span className="muted small" aria-live="polite">
          {streaming && follow ? '正在跟随最新输出' : streaming ? '已暂停跟随' : '输出结束'}
        </span>
        {!follow && streaming && (
          <button type="button" className="btn ghost small" onClick={jumpToEnd}>
            跳到最新
          </button>
        )}
      </div>
      <pre className="log" ref={boxRef} onScroll={onScroll} tabIndex={0} aria-label={title}>
        {body.length === 0 ? (
          <span className="muted">等待进程输出…</span>
        ) : (
          body.map((line, index) => (
            <span key={index} className={line.error ? 'log-line log-error' : 'log-line'}>
              {line.text}
              {'\n'}
            </span>
          ))
        )}
      </pre>
    </div>
  );
}
