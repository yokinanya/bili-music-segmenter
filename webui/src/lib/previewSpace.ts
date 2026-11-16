interface Context { editing: boolean; blocked: boolean }

export function previewSpaceAction({ editing, blocked }: Context): 'native' | 'playback' {
  return editing || blocked ? 'native' : 'playback';
}
