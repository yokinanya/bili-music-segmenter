'use client';
import { Activity, useEffect } from 'react';
import { useWorkspace } from '@/lib/useWorkspace';
import { Button, IconButton, useMaterial } from './Material';
import { Icon, type IconName } from './Icon';
import { ThemeToggle } from './ThemeToggle';
import { Workbench } from './Workbench';
import { HistoryPanel } from './HistoryPanel';
import { UsagePage } from './UsagePage';
const NAV: { label: string; icon: IconName }[] = [{ label: '工作台', icon: 'work' }, { label: '历史', icon: 'history' }, { label: '用量', icon: 'chart' }];
export function Workspace() {
  const state = useWorkspace(), material = useMaterial();
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (!event.altKey || !['1', '2', '3'].includes(event.key)) return;
      event.preventDefault(); state.setPage(NAV[Number(event.key) - 1].label);
    };
    window.addEventListener('keydown', keyboard); return () => window.removeEventListener('keydown', keyboard);
  }, [state.setPage]);
  if (material !== 'ready') return <main className="loading" role="status">{material || '正在准备操作中心…'}</main>;
  return <div className="app-shell"><a className="skip-link" href="#main-content">跳到主要内容</a><nav className="navigation" aria-label="主导航"><div className="brand-mark" aria-label="自动歌切"><Icon name="music" /></div>
    {NAV.map((item, index) => <Button key={item.label} variant="text" className={`nav-item ${state.page === item.label ? 'selected' : ''}`} aria-current={state.page === item.label ? 'page' : undefined} onClick={() => state.setPage(item.label)} title={`${item.label} · Alt+${index + 1}`}><span className="nav-icon"><Icon name={item.icon} /></span>{item.label}</Button>)}</nav>
    <main id="main-content" className="main" tabIndex={-1}><header className="topbar"><h1>{state.page === '工作台' ? '工具操作中心' : state.page === '历史' ? '任务历史' : '用量与费用'}</h1><ThemeToggle /></header>
      {state.error && <div className="error" role="alert">{state.error}{!state.options && <Button onClick={() => void state.bootstrap()}>重新连接</Button>}</div>}
      <Activity mode={state.page === '工作台' ? 'visible' : 'hidden'}><Workbench state={state} /></Activity>
      <Activity mode={state.page === '历史' ? 'visible' : 'hidden'}><HistoryPanel onRerun={state.rerun} onResume={state.track} onRedownload={state.redownload} selectedId={state.navigation.history || null} onSelect={(id) => state.navigate({ history: id ?? '' })} view={state.navigation.historyView} onView={(historyView) => state.navigate({ historyView })} /></Activity>
      <Activity mode={state.page === '用量' ? 'visible' : 'hidden'}><UsagePage currentId={state.currentId} /></Activity>
    </main>
    {state.current.notice && <div role="status" className="snackbar">{state.current.notice}<IconButton label="关闭通知" onClick={state.current.dismiss}><Icon name="close" /></IconButton></div>}
  </div>;
}
