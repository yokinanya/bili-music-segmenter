export const ICON_GRID = 24;
export const ICON_STROKE = 1.5;
export const ICON_SIZE_TOKENS = { xs: 14, sm: 16, md: 18, lg: 20, xl: 24 } as const;

/** All icons share one grid, one stroke width and one optical box: 20x20 centered at (12,12). */
export interface IconGeometry {
  readonly path: string;
  readonly grid: typeof ICON_GRID;
  readonly stroke: typeof ICON_STROKE;
  readonly filled?: boolean;
}

const icon = (path: string, extra: { filled?: boolean } = {}): IconGeometry =>
  ({ path, grid: ICON_GRID, stroke: ICON_STROKE, ...extra });

export const icons = {
  work: icon('M3 5h18v14H3zM8 5v14m0-9h13m-9 4h5'),
  history: icon('M12 4a8 8 0 1 0 8 8M12 4a8 8 0 0 1 5.9 2.6m2.1 5.4h-3.5m-6-4.4V12l2.6 1.6'),
  chart: icon('M4 20V10m8 10V4m8 16v-7'),
  upload: icon('M12 16V4m-4.5 4.5L12 4l4.5 4.5M4 15v5h16v-5'),
  play: icon('m8 5 9 7-9 7z', { filled: true }),
  close: icon('m6 6 12 12M6 18 18 6'),
  up: icon('m6 15 6-6 6 6'),
  down: icon('m6 9 6 6 6-6'),
  edit: icon('M5 19.8h3.2L19 9a2.8 2.8 0 0 0-4-4L4.2 16.2zM13.4 7l4.2 4.2'),
  retry: icon('M12 6.4h7.9m-7.9 0a6.85 6.85 0 1 0 5.15 10.05M12 6.4l3.1 3.1M12 6.4l3.1-3.1'),
  download: icon('M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4'),
  save: icon('M4 4h12l4 4v12H4zM8 4v5h8V4M8 20v-7h8v7'),
  music: icon('M9.5 17.5V6L18.5 4v11m-9 2.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0m9-2.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0M9.5 9.25 18.5 7.25'),
  stop: icon('M6 6h12v12H6z', { filled: true }),
  check: icon('m5 12 4.5 4.5L19 7'),
  pause: icon('M8 5v14m8-14v14'),
  volume: icon('M4 9.5h3.5L12 6v12l-4.5-3.5H4zM14.5 9.5a3 3 0 0 1 0 5m2.5-8.5a7 7 0 0 1 0 12'),
  muted: icon('M3.5 9h4l4.5-3.5v13L7.5 15h-4zm12.5 0 4.5 4.5m0-4.5-4.5 4.5'),
  fullscreen: icon('M4 9V4h5m6 0h5v5M4 15v5h5m11-5v5h-5'),
  system: icon('M4 4h16v12H4zM9 20h6m-3-4v4'),
  light: icon('M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8m0-5v2m0 14v2M3 12h2m14 0h2M6 6l1.4 1.4m9.2 9.2L18 18M6 18l1.4-1.4m9.2-9.2L18 6'),
  dark: icon('M19 14.5a7 7 0 0 1-9.5-9.5 7.5 7.5 0 1 0 9.5 9.5z'),
  scissors: icon('M5.75 5.75a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0m0 12.5a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0m4.4-10.6 8 6.6m-8 4.4 8-6.6'),
  settings: icon('M12 9.4a2.6 2.6 0 1 0 0 5.2 2.6 2.6 0 0 0 0-5.2m6.6 4.5a5.8 5.8 0 0 0 0-2.8l1.7-1.3-1.7-3-2.1.9a5.8 5.8 0 0 0-2.4-1.4L13.7 4h-3.4l-.4 2.3a5.8 5.8 0 0 0-2.4 1.4l-2.1-.9-1.7 3 1.7 1.3a5.8 5.8 0 0 0 0 2.8l-1.7 1.3 1.7 3 2.1-.9a5.8 5.8 0 0 0 2.4 1.4l.4 2.3h3.4l.4-2.3a5.8 5.8 0 0 0 2.4-1.4l2.1.9 1.7-3z'),
  'arrow-left': icon('M20 12H4m6-6-6 6 6 6'),
  'arrow-right': icon('M4 12h16m-6-6 6 6-6 6'),
  plus: icon('M12 5v14M5 12h14'),
  minus: icon('M5 12h14'),
  trash: icon('M4 7h16m-10 4v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3'),
  split: icon('M12 3v18M5 8h5v8H5zm9 0h5v8h-5z'),
  magnet: icon('M5 4h5v9a2 2 0 0 0 4 0V4h5v9a7 7 0 0 1-14 0zM5 8h5m4 0h5'),
  'mark-in': icon('M10 4H5v16h5m3-8h7m-4-4-4 4 4 4'),
  'mark-out': icon('M14 4h5v16h-5M4 12h7M8 8l4 4-4 4'),
  merge: icon('M4 12h6m4 0h6M8 3l4 3-4 3m8 12-4-3 4-3'),
  undo: icon('M9.35 4.35 4.15 9.65h5.2M4.15 9.65h10.5a5 5 0 0 1 0 10'),
  redo: icon('M14.65 4.35 19.85 9.65h-5.2m5.2 0h-10.5a5 5 0 0 0 0 10'),
  image: icon('M3 4h18v16H3zM3 16l5-5 4 4 3-3 4 4'),
  target: icon('M12 5.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13m0 3.1a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8'),
  folder: icon('M3 6.5h7l2 3h9v8H3z'),
  search: icon('M10.6 5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11m3.9 8.9 4.5 4.5'),
  filter: icon('M3.5 5h17l-6.5 7.3v6.2l-4-1.8v-4.4z'),
  export: icon('M12 3v11m-4-4 4 4 4-4M4 17v3h16v-3'),
  sparkle: icon('M12 3v6m0 6v6M3 12h6m6 0h6M6.5 6.5l3 3m5 5 3 3m0-11-3 3m-5 5-3 3'),
  eye: icon('M3.3 12s3.4-5.4 8.7-5.4S20.7 12 20.7 12 17.3 17.4 12 17.4 3.3 12 3.3 12m8.7-2.4a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8'),
  wave: icon('M3 12h2m2-4v8m3-12v16m3-10v4m3-8v12m3-6h2'),
} as const;

export type IconName = keyof typeof icons;
