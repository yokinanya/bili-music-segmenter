interface Context { editing: boolean; button: boolean; adjustment: boolean; blocked: boolean }

export function previewSpaceAction({ editing, button, adjustment, blocked }: Context): 'native' | 'playback' {
  return editing || blocked || (button && !adjustment) ? 'native' : 'playback';
}
