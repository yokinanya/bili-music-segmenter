const paths = {
  work: 'M3 5h18v14H3zM8 5v14m0-9h13m-9 4h5',
  history: 'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v5l3 2',
  chart: 'M4 20V10m8 10V4m8 16v-7',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5',
  play: 'm9 5 11 7-11 7z', close: 'm6 6 12 12M6 18 18 6',
  up: 'm6 15 6-6 6 6', down: 'm6 9 6 6 6-6',
  retry: 'M20 7v5h-5m5 0a8 8 0 1 0-2 6',
  download: 'M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4',
  music: 'M9 17V5l11-2v12M9 9l11-2M9 17a3 3 0 1 1-3-3h3m11 1a3 3 0 1 1-3-3h3',
  stop: 'M6 6h12v12H6z', check: 'm5 12 4 4L19 6',
  pause: 'M8 5v14m8-14v14',
  volume: 'M3 9h4l5-4v14l-5-4H3zM16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',
  muted: 'M3 9h4l5-4v14l-5-4H3zm13 0 6 6m-6 0 6-6',
  fullscreen: 'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5',
  system: 'M3 4h18v13H3zM8 21h8m-4-4v4',
  light: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8m0-6v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1',
  dark: 'M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11z',
};
export type IconName = keyof typeof paths;
export function Icon({ name }: { name: IconName }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
