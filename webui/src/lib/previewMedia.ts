import type mpegts from 'mpegts.js';

export type PreviewType = 'native' | 'flv';
export interface PreviewSource {
  src: string | null;
  type?: PreviewType;
  duration?: number;
  onError: (message: string) => void;
}
interface AttachedSource extends PreviewSource { video: HTMLVideoElement; src: string }
const MILLISECONDS_PER_SECOND = 1000;

export function previewType(name: string): PreviewType {
  return name.toLowerCase().endsWith('.flv') ? 'flv' : 'native';
}

export function attachPreview(source: AttachedSource, library?: typeof mpegts): () => void {
  const { video, src, type, duration, onError } = source;
  if (type !== 'flv') {
    video.src = src;
    return () => { video.pause(); video.removeAttribute('src'); video.load(); };
  }
  if (!library?.isSupported()) throw new Error('当前浏览器不支持 FLV 所需的 MSE 播放，请使用支持的浏览器');
  const url = new URL(src, video.ownerDocument.baseURI).href;
  const player = library.createPlayer({ type: 'flv', url, isLive: false,
    duration: duration === undefined ? undefined : duration * MILLISECONDS_PER_SECOND }, {
    enableWorker: true, accurateSeek: true, seekType: 'range', autoCleanupSourceBuffer: true,
  });
  const dispose = () => { player.unload(); player.detachMediaElement(); player.destroy(); };
  const fail = (message: string) => { player.unload(); onError(message); };
  player.on(library.Events.ERROR, (_kind: string, detail: string, info: { msg?: string } = {}) => {
    fail(`原视频播放失败：${detail}${info.msg ? ` · ${info.msg}` : ''}`);
  });
  player.on(library.Events.MEDIA_INFO, (info: { hasKeyframesIndex?: boolean }) => {
    if (info.hasKeyframesIndex === false) fail('FLV 缺少关键帧索引，无法随机定位歌曲切点；请使用带索引的录像');
  });
  try {
    player.attachMediaElement(video);
    player.load();
  } catch (error) {
    dispose();
    throw error;
  }
  return dispose;
}
