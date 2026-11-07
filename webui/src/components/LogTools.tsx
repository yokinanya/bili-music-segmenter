import { Button } from './Material';
import { LogActions } from './LogActions';
import type { useLogNavigation } from './useLogNavigation';

type Navigation = ReturnType<typeof useLogNavigation>;

function LogSearch({ navigation }: { navigation: Navigation }) {
  const { keyword, matches, selected, navigate, search } = navigation;
  return <div className="log-search">
    <input aria-label="查找日志" type="search" value={keyword} placeholder="查找日志"
      onChange={event => search(event.target.value)}
      onKeyDown={event => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        navigate(event.shiftKey ? -1 : 1);
      }} />
    <Button variant="text" disabled={!matches.length} onClick={() => navigate(-1)}>上一个</Button>
    <Button variant="text" disabled={!matches.length} onClick={() => navigate(1)}>下一个</Button>
    {keyword && <span role="status">{selected + 1} / {matches.length} 个匹配</span>}
  </div>;
}

function LogPagination({ navigation }: { navigation: Navigation }) {
  const { currentPage, pages, changePage } = navigation;
  if (pages <= 1) return null;
  return <div className="log-pagination">
    <Button variant="text" disabled={!currentPage} onClick={() => changePage(currentPage - 1)}>上一页</Button>
    <label>历史页 <input aria-label="日志历史页" type="number" min={1} max={pages} value={currentPage + 1}
      onChange={event => {
        const value = Number(event.target.value);
        if (Number.isInteger(value) && value >= 1 && value <= pages) changePage(value - 1);
      }} /> / {pages}</label>
    <Button variant="text" disabled={currentPage >= pages - 1} onClick={() => changePage(currentPage + 1)}>下一页</Button>
  </div>;
}

export function LogTools({ jobId, index, navigation }: { jobId: string; index: number; navigation: Navigation }) {
  return <>
    <LogSearch navigation={navigation} />
    <LogPagination navigation={navigation} />
    <LogActions jobId={jobId} index={index} />
  </>;
}
