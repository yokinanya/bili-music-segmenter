import { useMemo, useState } from 'react';
import { findLog, PAGE_ROWS, rowAt, type LogBuffer } from './logBuffer';

export function useLogNavigation(buffer: LogBuffer) {
  const [follow, setFollow] = useState(true);
  const [page, setPage] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [selection, setSelection] = useState(-1);
  const matches = useMemo(() => findLog(buffer, keyword), [buffer, keyword]);
  const selected = selection >= 0 && matches.length ? Math.min(selection, matches.length - 1) : -1;
  const match = selected < 0 ? -1 : matches[selected];
  const pages = Math.max(1, Math.ceil(buffer.rows.length / PAGE_ROWS));
  const currentPage = follow ? pages - 1 : Math.min(page, pages - 1);
  const changePage = (value: number) => {
    setFollow(false);
    setSelection(-1);
    setPage(value);
  };
  const navigate = (direction: number) => {
    if (!matches.length) return;
    const first = direction > 0 ? 0 : matches.length - 1;
    const next = selected < 0 ? first : (selected + direction + matches.length) % matches.length;
    setSelection(next);
    setFollow(false);
    setPage(Math.floor(rowAt(buffer.rows, matches[next]) / PAGE_ROWS));
  };
  const search = (value: string) => {
    setKeyword(value);
    setSelection(-1);
  };
  const toggleFollow = () => {
    setPage(currentPage);
    setFollow(value => !value);
    setSelection(-1);
  };
  const pause = () => {
    setPage(currentPage);
    setFollow(false);
  };
  return { follow, keyword, selected, match, matches, pages, currentPage, changePage, navigate, search, toggleFollow, pause };
}
