'use client';
import { useCallback, useRef, useState } from 'react';
import { initialPlayback, isInterruption, progressFraction, scrubFromPointer, scrubTime } from '@/lib/playback';
import { usePointerSeek } from '@/lib/usePointerSeek';
import { usePreviewSource } from '@/lib/usePreviewSource';
import type { PreviewType } from '@/lib/previewMedia';
import { mediaTime as clock } from '@/lib/format';
import { PreviewVolume } from './PreviewVolume';
import { IconButton } from './Material';
import { Icon } from './Icon';

interface Props {
  src: string | null;
  type?: PreviewType;
  duration?: number;
  stopAt?: number;
  onTime: (time: number) => void;
  onSeek?: (time: number) => void;
  onError: (message: string) => void;
  registerVideo: (element: HTMLVideoElement | null) => void;
}

function useTransport({ onTime, onSeek, onError, registerVideo }: Props) {
  const video = useRef<HTMLVideoElement>(null), bar = useRef<HTMLDivElement>(null);
  const resume = useRef(false);
  const [state, setState] = useState(initialPlayback);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'waiting' | 'error'>('loading');
  const attach = useCallback((element: HTMLVideoElement | null) => {
    video.current = element;
    registerVideo(element);
  }, [registerVideo]);
  const play = () => {
    const element = video.current;
    if (!element) return;
    void element.play().catch((error: unknown) => {
      if (!isInterruption(error)) onError(error instanceof Error ? error.message : String(error));
    });
  };
  const seek = (time: number) => {
    const element = video.current;
    if (!element || element.readyState === 0) return;
    const target = scrubTime(time, element.duration);
    element.currentTime = target;
    setState(current => ({ ...current, time: target }));
    (onSeek ?? onTime)(target);
  };
  const pointer = usePointerSeek({
    enabled: state.duration > 0,
    onSeek: x => { if (bar.current) seek(scrubFromPointer(x, bar.current.getBoundingClientRect(), state.duration)); },
    onStart: () => { resume.current = !!video.current && !video.current.paused; video.current?.pause(); },
    onEnd: () => { if (resume.current) play(); resume.current = false; },
  });
  return { video, bar, state, setState, phase, setPhase, attach, play, seek, pointer };
}

export function PreviewTransport(props: Props) {
  const playbackBoundary = useRef<number | null>(null);
  const transport = useTransport(props);
  const { video, bar, state, setState, phase, setPhase, attach, play, seek, pointer } = transport;
  usePreviewSource(video, { src: props.src, type: props.type, duration: props.duration,
    onError: message => { setPhase('error'); props.onError(message); } });
  const metadata = (event: React.SyntheticEvent<HTMLVideoElement>) => {
    const duration = event.currentTarget.duration;
    setState(current => ({ ...current, duration }));
    setPhase('ready');
  };
  const percent = progressFraction(state.time, state.duration) * 100;
  const updateTime = (element: HTMLVideoElement) => {
    let time = element.currentTime;
    if (!element.paused && !element.seeking && playbackBoundary.current !== null && time >= playbackBoundary.current) {
      element.pause();
      time = playbackBoundary.current;
      playbackBoundary.current = null;
      element.currentTime = time;
    }
    setState(current => ({ ...current, time }));
    props.onTime(time);
  };
  return <>
    <div className="preview-stage">
      {props.src ? <video ref={attach} playsInline preload="metadata"
        onLoadedMetadata={metadata} onCanPlay={() => setPhase('ready')} onWaiting={() => setPhase('waiting')}
        onTimeUpdate={event => updateTime(event.currentTarget)}
        onPlay={event => {
          playbackBoundary.current = props.stopAt !== undefined && event.currentTarget.currentTime < props.stopAt ? props.stopAt : null;
          setState(current => ({ ...current, intent: 'playing', pending: true }));
        }}
        onPlaying={() => { setPhase('ready'); setState(current => ({ ...current, intent: 'playing', pending: false })); }}
        onPause={() => setState(current => ({ ...current, intent: 'paused', pending: false }))}
        onEnded={() => setState(current => ({ ...current, intent: 'paused', pending: false }))}
        onError={event => { setPhase('error'); props.onError(`原视频播放失败：${event.currentTarget.error?.message || '浏览器不支持此容器或编码'}`); }} />
        : !props.src && <div className="preview-empty"><strong>还没有导入录像</strong></div>}
      {props.src && (phase === 'loading' || phase === 'waiting') && <div className="preview-status" role="status">
        {phase === 'loading' ? '正在加载原视频…' : '正在缓冲…'}
      </div>}
    </div>
    <div className="preview-bar">
      <span className="timecode">{clock(state.time)} / {clock(state.duration)}</span>
      <IconButton className="preview-play-toggle" label={state.intent === 'playing' ? '暂停' : '播放'} disabled={!state.duration}
        onPointerDown={event => event.preventDefault()}
        onClick={() => { if (video.current?.paused) play(); else video.current?.pause(); }}><Icon name={state.intent === 'playing' ? 'pause' : 'play'} /></IconButton>
      <div className="scrub" ref={bar} role="slider" tabIndex={0} aria-label="播放进度" aria-disabled={!state.duration}
        aria-valuemin={0} aria-valuemax={Math.round(state.duration)} aria-valuenow={Math.round(state.time)}
        aria-valuetext={`${clock(state.time)} / ${clock(state.duration)}`} {...pointer}
        onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); seek(state.time + (event.key === 'ArrowLeft' ? -5 : 5)); } }}>
        <i style={{ width: `${percent}%` }} /><b style={{ left: `${percent}%` }} />
      </div>
      <PreviewVolume video={video} disabled={!props.src} />
    </div>
  </>;
}
