import type { Clip } from './types';

/** Clip names embed the source media stem; keep the separation explicit instead of guessing. */
export function clipsFor(clips: Clip[], media: string | undefined): Clip[] {
  if (!media) return clips;
  const stem = media.replace(/\.[^.]+$/, '');
  const marker = `_${stem}_`;
  const matched = clips.filter((clip) => clip.name.includes(marker));
  return matched.length > 0 ? matched : clips;
}
