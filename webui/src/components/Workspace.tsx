'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { clipsFor } from '@/lib/clips';
import type { Bootstrap, HistoryEntry, InputFile, UsageSnapshot } from '@/lib/types';
import { useJob } from '@/lib/useJob';
import { BatchProgress } from './BatchProgress';
import { ConfirmDialog } from './ConfirmDialog';
import { FilePicker } from './FilePicker';
import { HistoryPanel } from './HistoryPanel';
import { LogViewer } from './LogViewer';
import { STATE_LABELS, StateBadge } from './StateBadge';
import { ThemeToggle } from './ThemeToggle';
import { ToastStack, useToasts } from './Toasts';
import { UsagePanel } from './UsagePanel';

const JOB_KEY = 'bms-job';
const OUTDIR_KEY = 'bms-outdir';

export function Workspace() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [files, setFiles] = useState<InputFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(true);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [outdir, setOutdir] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [activeItem, setActiveItem] = useState(0);
  const [sessionUsage, setSessionUsage] = useState<UsageSnapshot | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [serverDown, setServerDown] = useState(false);
  const [staleToken, setStaleToken] = useState(false);
  const { toasts, push, dismiss } = useToasts();
  const feed = useJob(jobId);
  const filterRef = useRef<HTMLInputElement>(null);

  const status = feed.status;
  const running = status?.state === 'running' || (!status && jobId !== null && feed.connection !== 'offline');
  const hasClips = (status?.clips.length ?? 0) > 0;
  const canStart = selected.length > 0 && !running && !starting;
  const clips = useMemo(() => clipsFor(status?.clips ?? [], status?.batch[activeItem]?.media), [status, activeItem]);

  const loadFiles = useCallback(
    async (clearSelection = false) => {
      setFilesLoading(true);
      setFilesError(null);
      try {
        const data = await api.inputs();
        setServerDown(false);
        setFiles(data.files);
        setSelected((current) => {
          const available = new Set(data.files.map((file) => file.name));
          if (clearSelection) return [];
          return current.filter((name) => available.has(name));
        });
      } catch (cause) {
        const message = cause instanceof ApiError ? cause.message : '未知错误';
        setFilesError(message);
        setServerDown(cause instanceof ApiError && cause.status === 0);
        // 403 without a running job means the service restarted and issued a new token.
        setStaleToken(cause instanceof ApiError && cause.status === 403);
      } finally {
        setFilesLoading(false);
      }
    },
    [],
  );

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.history();
      setHistory(data.entries);
    } catch {
      // History is a convenience list; keep the current page usable when it fails.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.bootstrap();
        if (cancelled) return;
        setBoot(data);
        setOutdir(window.localStorage.getItem(OUTDIR_KEY) ?? data.output_dir);
        const stored = window.sessionStorage.getItem(JOB_KEY);
        if (stored) setJobId(stored);
      } catch (cause) {
        if (!cancelled) setBootError(cause instanceof ApiError ? cause.message : '未知错误');
      }
    })();
    void loadFiles();
    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [loadFiles, loadHistory]);

  // Session usage is a slow-moving aggregate; refresh it far less often than the job itself.
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const data = await api.usage();
        if (cancelled) return;
        setSessionUsage(data);
        // A successful call is proof the service is back and the token is valid.
        setServerDown(false);
        setStaleToken(false);
      } catch (cause) {
        if (cancelled || !(cause instanceof ApiError)) return;
        if (cause.status === 0) setServerDown(true);
        if (cause.status === 403) setStaleToken(true);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!jobId) return;
    window.sessionStorage.setItem(JOB_KEY, jobId);
  }, [jobId]);

  // Follow the file being processed unless the user picked one explicitly.
  useEffect(() => {
    if (!status) return;
    const index = status.batch.findIndex((item) => item.state === 'running');
    if (index >= 0) setActiveItem(index);
  }, [status]);

  useEffect(() => {
    if (!status) return;
    const settled = status.state !== 'running' && status.batch_complete;
    if (!settled) return;
    window.sessionStorage.removeItem(JOB_KEY);
    setSelected([]);
    void loadHistory();
    if (status.state === 'succeeded') push(`批次完成：导出 ${status.clips.length} 个片段`, 'success');
    if (status.state === 'failed') push('批次中有文件失败，请查看日志', 'error');
  }, [status, loadHistory, push]);

  useEffect(() => {
    if (feed.connection === 'offline') {
      window.sessionStorage.removeItem(JOB_KEY);
      push('任务已不存在（服务可能已重启）', 'error');
      setJobId(null);
    }
  }, [feed.connection, push]);

  const start = useCallback(async () => {
    if (!canStart) return;
    setStarting(true);
    try {
      window.localStorage.setItem(OUTDIR_KEY, outdir);
      const data = await api.start(selected, outdir.trim());
      setJobId(data.id);
      setActiveItem(0);
      push(`已开始处理 ${selected.length} 个文件`, 'info');
    } catch (cause) {
      push(cause instanceof ApiError ? cause.message : '启动失败', 'error');
    } finally {
      setStarting(false);
    }
  }, [canStart, selected, outdir, push]);

  const stop = useCallback(async () => {
    if (!jobId) return;
    setConfirmStop(false);
    setStopping(true);
    try {
      await api.stop(jobId);
      push('已请求停止：将结束当前文件并跳过剩余文件', 'info');
    } catch (cause) {
      push(cause instanceof ApiError ? cause.message : '停止失败', 'error');
    } finally {
      setStopping(false);
    }
  }, [jobId, push]);

  // Keyboard shortcuts: Ctrl/Cmd+Enter starts, Ctrl/Cmd+. stops, Ctrl/Cmd+K focuses the filter.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const meta = event.ctrlKey || event.metaKey;
      if (meta && event.key === 'Enter') {
        event.preventDefault();
        void start();
      } else if (meta && event.key === '.') {
        event.preventDefault();
        if (running && jobId) setConfirmStop(true);
      } else if (meta && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        filterRef.current?.focus();
        filterRef.current?.select();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [start, running, jobId]);

  const openHistory = (entry: HistoryEntry) => {
    setJobId(entry.id);
    setActiveItem(0);
  };

  const rerun = (entry: HistoryEntry) => {
    const available = new Set(files.map((file) => file.name));
    const usable = entry.medias.filter((name) => available.has(name));
    if (usable.length === 0) {
      push('输入目录中已找不到这些文件，请重新放入后再试', 'error');
      return;
    }
    setSelected(usable);
    setOutdir(entry.outdir);
    push(`已选中 ${usable.length} 个文件，按 Ctrl/Cmd+Enter 开始`, 'info');
  };

  const connectionText = feed.connection === 'retrying' ? `连接中断，正在重试：${feed.lastError ?? ''}` : null;
  const connectionLabel =
    serverDown || feed.connection === 'offline'
      ? '服务不可达'
      : feed.connection === 'retrying'
        ? '连接中断，正在重试'
        : feed.connection === 'online'
          ? '服务已连接'
          : '空闲';
  const itemLogs = status ? feed.logs[activeItem] ?? '' : '';

  return (
    <>
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <div className="shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">BILI MUSIC SEGMENTER</p>
            <h1>API 自动歌切</h1>
          </div>
          <div className="topbar-actions">
            <span className={`conn conn-${serverDown ? 'offline' : feed.connection}`} aria-live="polite">
              {connectionLabel}
            </span>
            <ThemeToggle />
          </div>
        </header>

        {staleToken && (
          <div className="notice danger" role="alert">
            访问令牌已失效：服务重启后会生成新令牌。请从启动日志中复制新的 WebUI 地址，或刷新本页。
            <button type="button" className="btn ghost small" onClick={() => window.location.reload()}>
              刷新页面
            </button>
          </div>
        )}

        {serverDown && (
          <div className="notice danger" role="alert">
            本地服务不可达。请确认 <code>uv run --group api -m segment.webui</code> 仍在运行；服务恢复后页面会自动重连。
          </div>
        )}

        {bootError && (
          <div className="notice danger" role="alert">
            无法连接本地服务：{bootError}。请确认 `uv run --group api -m segment.webui` 仍在运行。
            <button type="button" className="btn ghost small" onClick={() => window.location.reload()}>
              重新加载
            </button>
          </div>
        )}

        <main id="main" className="layout">
          <div className="column">
            <section className="card" aria-labelledby="run-title">
              <div className="card-head">
                <h2 id="run-title">处理设置</h2>
                {status && <StateBadge state={status.state} />}
              </div>
              <label className="field">
                <span>输出目录</span>
                <input
                  className="input"
                  value={outdir}
                  onChange={(event) => setOutdir(event.target.value)}
                  disabled={running}
                  spellCheck={false}
                />
              </label>
              <p className="hint">
                开始前请配置项目根目录的 .env 并确保 FFmpeg 可用。处理会调用云端 API 与 S3 兼容存储，产生相应费用。
              </p>
              <div className="actions">
                <button
                  type="button"
                  className="btn primary"
                  onClick={() => void start()}
                  disabled={!canStart}
                >
                  {starting ? '正在启动…' : running ? '处理中…' : `开始歌切${selected.length ? `（${selected.length}）` : ''}`}
                </button>
                {running && (
                  <button type="button" className="btn danger" onClick={() => setConfirmStop(true)} disabled={stopping}>
                    停止
                  </button>
                )}
                <span className="muted small">
                  <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>Enter</kbd> 开始 · <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>.</kbd> 停止 ·{' '}
                  <kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>K</kbd> 筛选
                </span>
              </div>
              {connectionText && (
                <p className="notice warn" role="alert">
                  {connectionText}
                  <button type="button" className="btn ghost small" onClick={feed.retry}>
                    立即重试
                  </button>
                </p>
              )}
            </section>

            <FilePicker
                filterInputRef={filterRef}
                directory={boot?.input_dir ?? ''}
                files={files}
                loading={filesLoading}
                error={filesError}
                selected={selected}
                disabled={running}
                onChange={setSelected}
                onRefresh={() => void loadFiles()}
              />

            {status && (
              <BatchProgress
                status={status}
                activeIndex={activeItem}
                clips={clips}
                jobId={jobId ?? ''}
                onSelectItem={setActiveItem}
              />
            )}
          </div>

          <div className="column">
            <section className="card" aria-labelledby="log-title">
              <div className="card-head">
                <h2 id="log-title">处理日志</h2>
                {status && (
                  <span className="muted small">
                    {status.batch[activeItem]?.media ?? ''} · {STATE_LABELS[status.batch[activeItem]?.state ?? 'pending']}
                  </span>
                )}
              </div>
              <LogViewer
                text={itemLogs}
                streaming={status?.batch[activeItem]?.state === 'running'}
                title={`${status?.batch[activeItem]?.media ?? '任务'} 的日志`}
              />
              {jobId && hasClips && (
                <p className="muted small">
                  片段与 JSON 记录保存在 <code>{status?.outdir}</code>
                </p>
              )}
            </section>
            <UsagePanel session={sessionUsage} job={status?.usage ?? null} />
            <HistoryPanel entries={history} currentId={jobId} onOpen={openHistory} onRerun={rerun} />
          </div>
        </main>
      </div>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <ConfirmDialog
        open={confirmStop}
        title="停止当前任务？"
        description="正在处理的文件会被终止，剩余文件将被跳过。已经导出的片段会保留。"
        confirmLabel="停止任务"
        tone="danger"
        onConfirm={() => void stop()}
        onCancel={() => setConfirmStop(false)}
      />
    </>
  );
}
