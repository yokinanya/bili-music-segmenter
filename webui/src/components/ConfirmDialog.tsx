'use client';

import { useEffect, useRef } from 'react';

interface Props {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: 'default' | 'danger';
  onConfirm: () => void;
  onCancel: () => void;
}

/** Native <dialog> keeps focus inside and restores it on close without extra code. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = '取消',
  tone = 'default',
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="confirm" onCancel={onCancel} onClose={onCancel}>
      <h2>{title}</h2>
      <p className="muted">{description}</p>
      <div className="confirm-actions">
        <button type="button" className="btn ghost" onClick={onCancel}>
          {cancelLabel}
        </button>
        <button type="button" className={tone === 'danger' ? 'btn danger' : 'btn primary'} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
