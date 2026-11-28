'use client';
import { useEffect, useState } from 'react';
import { IconButton } from './Material';
import { Icon } from './Icon';

const SAVED_VISIBLE_MS = 1200;
const labels = { idle: '保存', saving: '正在保存…', saved: '草稿已保存' };
type SaveState = keyof typeof labels;

interface Props {
  disabled: boolean;
  onSave: (onSaved: () => void) => Promise<void>;
}

export function DraftSaveButton({ disabled, onSave }: Props) {
  const [state, setState] = useState<SaveState>('idle');
  useEffect(() => {
    if (state !== 'saved') return;
    const timer = window.setTimeout(() => setState('idle'), SAVED_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [state]);

  const save = async () => {
    setState('saving');
    try {
      await onSave(() => setState('saved'));
    } finally {
      setState(current => current === 'saving' ? 'idle' : current);
    }
  };

  return <>
    <IconButton className="draft-save-button" variant="filled" label={labels[state]} data-state={state}
      disabled={disabled || state === 'saving'} aria-busy={state === 'saving'} onClick={() => void save()}>
      <span className="draft-save-glyphs" aria-hidden="true">
        <span data-glyph="idle"><Icon name="save" /></span>
        <span data-glyph="saving"><span className="draft-save-spinner" /></span>
        <span data-glyph="saved"><Icon name="check" /></span>
      </span>
    </IconButton>
    <span className="draft-save-status" role="status">{state === 'idle' ? '' : labels[state]}</span>
  </>;
}
