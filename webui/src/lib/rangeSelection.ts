interface Options { ids: readonly string[]; anchor: string | null; target: string }

export function selectSongRange({ ids, anchor, target }: Options): string[] {
  const end = ids.indexOf(target), start = anchor === null ? -1 : ids.indexOf(anchor);
  if (end < 0) throw new Error('选中的歌曲已不存在');
  if (start < 0) return [target];
  return ids.slice(Math.min(start, end), Math.max(start, end) + 1);
}
