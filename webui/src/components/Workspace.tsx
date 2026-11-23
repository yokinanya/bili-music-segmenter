'use client';
import { useEffect, useState } from 'react';
import { bindPageZoomPrevention } from '@/lib/timelineZoom';
import { useWorkspace } from '@/lib/useWorkspace';
import { Button, useMaterial } from './Material';
import { Icon, type IconName } from './Icon';
import { ThemeToggle } from './ThemeToggle';
import { Workbench } from './Workbench';
import { ClearHistoryButton } from './HistoryPanel';
import { UsagePage } from './UsagePage';
import { SongConsole } from './SongConsole';
import { TaskSettings } from './TaskSettings';
import { CacheSettings } from './CacheSettings';
import './editor-shell.css';

const PAGES: Record<string, { title: string; rail: string; icon: IconName }> = {
  工作台: { title: '歌切剪辑台', rail: '歌切', icon: 'scissors' },
  链接下载: { title: '链接下载', rail: '链接', icon: 'download' },
  历史: { title: '历史任务', rail: '历史', icon: 'history' },
  用量: { title: '用量与费用', rail: '用量', icon: 'chart' },
  设置: { title: '设置', rail: '设置', icon: 'settings' },
};

export function Workspace() {
  const state = useWorkspace(), material = useMaterial();
  const [editorActions, setEditorActions] = useState<HTMLSpanElement | null>(null);
  useEffect(() => bindPageZoomPrevention(document), []);
  if (material !== 'ready') return <main className="loading" role="status">{material || '正在准备歌切工作台…'}</main>;
  const page = PAGES[state.page] ? state.page : '工作台';
  return <div className="app-shell editor-shell">
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <nav className="tool-rail" aria-label="工具">
      <button className="rail-logo" aria-label="回到歌切剪辑台" onClick={() => state.setPage('工作台')}><Icon name="music" size="md" /></button>
      {(['工作台', '链接下载', '用量'] as const).map(name => <RailButton key={name} click={() => state.setPage(name)} page={name} current={page} />)}
      <span className="rail-spacer" />
      <RailButton click={() => state.setPage('设置')} page="设置" current={page} />
    </nav>
    <div className="editor-column">
      <header className="editor-appbar">
        <button className="appbar-project" onClick={() => state.setPage('工作台')}><Icon name="music" size="sm" /><span>{PAGES[page].title}</span></button>
        <span className="appbar-actions"><span className="editor-actions" ref={setEditorActions} hidden={page !== '工作台'} /><ThemeToggle /></span>
      </header>
      <main id="main-content" className="editor-main" tabIndex={-1}>
        {state.error && <div className="error" role="alert">{state.error}{!state.options && <Button onClick={() => void state.bootstrap()}>重新连接</Button>}</div>}
        <div className="editor-view" hidden={page !== '工作台'}><SongConsole toolbarTarget={editorActions} /></div>
        <div className="editor-view editor-flow" hidden={page !== '链接下载'}><Workbench state={state}  /></div>

        <div className="editor-view editor-flow" hidden={page !== '用量'}><UsagePage /></div>
        <div className="editor-view editor-flow" hidden={page !== '设置'}>
          <TaskSettings options={state.options} onSaved={state.setOptions} />
          <CacheSettings />
          <section className="settings-card"><h2>任务记录</h2><p className="helper">清除后只删除任务记录，已导出的视频和导入的素材保留在磁盘。</p><ClearHistoryButton /></section>
        </div>
        {state.current.notice && <div role="status" className="snackbar">{state.current.notice}<button aria-label="关闭通知" onClick={state.current.dismiss}><Icon name="close" size="sm" /></button></div>}
      </main>
    </div>
  </div>;
}

function RailButton({ click, page, current }: { click: () => void; page: string; current: string }) {
  return <button className="rail-button" aria-pressed={page === current} title={PAGES[page].rail} onClick={click}><Icon name={PAGES[page].icon} /><span>{PAGES[page].rail}</span></button>;
}
