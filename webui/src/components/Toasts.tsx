'use client';

import { useCallback, useRef, useState } from 'react';

export type ToastTone = 'info' | 'success' | 'error';

export interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

/** Small transient message stack; errors stay longer because they usually need reading. */
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, message, tone }]);
      window.setTimeout(() => dismiss(id), tone === 'error' ? 8000 : 4000);
      return id;
    },
    [dismiss],
  );

  return { toasts, push, dismiss };
}

export function ToastStack({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tone}`} role={toast.tone === 'error' ? 'alert' : undefined}>
          <span>{toast.message}</span>
          <button type="button" className="toast-close" onClick={() => onDismiss(toast.id)} aria-label="关闭提示">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
