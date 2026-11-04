export function bytes(value: number) { const index = Math.min(Math.floor(Math.log(Math.max(1, value)) / Math.log(1024)), 3); return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${['B', 'KB', 'MB', 'GB'][index]}`; }
export function elapsed(start: string | null, end: string | null = null) { if (!start) return '—'; const seconds = Math.max(0, Math.round(((end ? Date.parse(end) : Date.now()) - Date.parse(start)) / 1000)); return `${Math.floor(seconds / 60)}分 ${seconds % 60}秒`; }
export const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
