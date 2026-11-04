import { useSyncExternalStore } from 'react';
import type { DialogAnimation } from '@material/web/dialog/internal/animations.js';

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
const ENTER_MS = 250, EXIT_MS = 150;
function subscribe(onChange: () => void) {
  const media = window.matchMedia(REDUCED_MOTION);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}
export function useReducedMotion() {
  return useSyncExternalStore(subscribe, () => window.matchMedia(REDUCED_MOTION).matches, () => false);
}
export function dialogAnimation({ opening, reduced }: { opening: boolean; reduced: boolean }): DialogAnimation {
  const duration = opening ? ENTER_MS : EXIT_MS;
  const from = { opacity: opening ? 0 : 1, transform: opening ? 'scale(.96)' : 'scale(1)' };
  const to = { opacity: opening ? 1 : 0, transform: opening ? 'scale(1)' : 'scale(.98)' };
  if (reduced) { from.transform = 'none'; to.transform = 'none'; }
  return {
    dialog: [[[from, to], { duration, easing: 'cubic-bezier(.2,0,0,1)' }]],
    scrim: [[[{ opacity: opening ? 0 : .32 }, { opacity: opening ? .32 : 0 }], { duration }]],
  };
}
