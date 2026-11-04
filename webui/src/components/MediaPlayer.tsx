'use client';
import { useRef, useState } from 'react';
import { errorText } from '@/lib/format';
import { Button, IconButton, Slider } from './Material';
import { Icon } from './Icon';

function timestamp(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
export function MediaPlayer({ src, label }: { src: string; label: string }) {
  const video = useRef<HTMLVideoElement>(null), frame = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false), [muted, setMuted] = useState(false);
  const [time, setTime] = useState(0), [duration, setDuration] = useState(0), [error, setError] = useState('');
  const act = async (work: () => Promise<void> | void) => {
    try { await work(); setError(''); } catch (cause) { setError(errorText(cause)); }
  };
  const toggle = () => act(() => playing ? video.current!.pause() : video.current!.play());
  return <div className='media-player' ref={frame} aria-label={label}>
    <div className='media-frame'>
      <video ref={video} playsInline preload='metadata' src={src} aria-label={label}
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
        onError={(event) => setError(event.currentTarget.error?.message || '视频加载失败')} />
      <IconButton className='media-overlay' label={playing ? '暂停' : '播放'} onClick={() => void toggle()}><Icon name={playing ? 'pause' : 'play'} /></IconButton>
    </div>
    <div className='media-controls'>
      <IconButton label={playing ? '暂停' : '播放'} onClick={() => void toggle()}><Icon name={playing ? 'pause' : 'play'} /></IconButton>
      <span className='media-time'>{timestamp(time)} / {timestamp(duration)}</span>
      <IconButton label={muted ? '取消静音' : '静音'} onClick={() => { video.current!.muted = !muted; setMuted(!muted); }}><Icon name={muted ? 'muted' : 'volume'} /></IconButton>
      <IconButton label='全屏' onClick={() => void act(() => frame.current!.requestFullscreen())}><Icon name='fullscreen' /></IconButton>
    </div>
    <Slider label={`${label} 播放进度`} value={time} max={duration} step={0.1} disabled={!duration}
      onChange={(value) => { video.current!.currentTime = value; setTime(value); }} />
    {error && <div className='error' role='alert'>{error}<Button onClick={() => { setError(''); video.current!.load(); }}>重新加载</Button></div>}
  </div>;
}
