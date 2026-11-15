interface Interval { readonly id: string; readonly start_seconds: number; readonly end_seconds: number }
interface Options {
  readonly clips: readonly Interval[]; readonly selected: readonly string[]; readonly time: number;
  readonly keepEndpoint?: boolean; readonly preserveSelection?: boolean;
}

export function selectionAtTime({ clips, selected, time, keepEndpoint = false, preserveSelection = false }: Options): string[] {
  if (preserveSelection) return [...selected];
  const current = selected.length === 1 ? clips.find(clip => clip.id === selected[0]) : undefined;
  if (current && current.start_seconds <= time && (time < current.end_seconds || (keepEndpoint && time === current.end_seconds))) return [current.id];
  const covering = clips.filter(clip => clip.start_seconds <= time && time < clip.end_seconds);
  const latest = covering.reduce<Interval | undefined>((best, clip) => !best || clip.start_seconds > best.start_seconds ? clip : best, undefined);
  return latest ? [latest.id] : [];
}
