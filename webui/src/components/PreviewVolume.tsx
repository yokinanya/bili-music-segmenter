'use client';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { Icon } from './Icon';
import { IconButton, Slider } from './Material';

const VOLUME_PERCENT = 100;
const WHEEL_STEP = 5;

export function PreviewVolume({ video, disabled }: { video: RefObject<HTMLVideoElement | null>; disabled: boolean }) {
  const [audio, setAudio] = useState({ volume: 1, muted: false });
  const lastAudible = useRef(1);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    const sync = () => {
      if (element.volume > 0) lastAudible.current = element.volume;
      setAudio({ volume: element.volume, muted: element.muted });
    };
    sync();
    element.addEventListener('volumechange', sync);
    return () => element.removeEventListener('volumechange', sync);
  }, [video]);
  const toggle = () => {
    const element = video.current;
    if (!element) return;
    if (element.muted || element.volume === 0) {
      if (element.volume === 0) element.volume = lastAudible.current;
      element.muted = false;
    } else element.muted = true;
  };
  const silent = audio.muted || audio.volume === 0;
  const percent = silent ? 0 : Math.round(audio.volume * VOLUME_PERCENT);
  const adjustWithWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (disabled || event.deltaY === 0) return;
    event.preventDefault();
    const element = video.current;
    if (!element) return;
    const nextPercent = Math.max(0, Math.min(VOLUME_PERCENT,
      Math.round(element.volume * VOLUME_PERCENT) + (event.deltaY < 0 ? WHEEL_STEP : -WHEEL_STEP)));
    const volume = nextPercent / VOLUME_PERCENT;
    element.volume = volume;
    element.muted = false;
    if (volume > 0) lastAudible.current = volume;
    setAudio({ volume, muted: false });
  };
  return <div className="preview-volume" role="group" aria-label="预览音量" onWheel={adjustWithWheel}>
    <IconButton label={silent ? '取消静音' : '静音'} disabled={disabled} onClick={toggle} aria-pressed={silent}>
      <Icon name={silent ? 'muted' : 'volume'} size="sm" />
    </IconButton>
    <Slider label="播放音量" max={VOLUME_PERCENT} value={percent} disabled={disabled}
      onChange={value => {
        const element = video.current;
        if (!element) return;
        const volume = value / VOLUME_PERCENT;
        element.volume = volume;
        element.muted = false;
        if (volume > 0) lastAudible.current = volume;
        setAudio({ volume, muted: false });
      }} />
    <output className="volume-value" aria-hidden="true">{percent}%</output>
  </div>;
}
