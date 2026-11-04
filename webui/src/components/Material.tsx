'use client';
import { createElement, useEffect, useRef, useState, type ReactNode } from 'react';
import { dialogAnimation, useReducedMotion } from '@/lib/materialMotion';
export { ActionLink, Button, IconButton, ListButton } from './MaterialActions';

export function useMaterial() {
  const [state, setState] = useState('');
  useEffect(() => {
    Promise.all([
      import('@material/web/textfield/outlined-text-field.js'),
      import('./MaterialProgress'),
      import('@material/web/tabs/tabs.js'),
      import('@material/web/tabs/secondary-tab.js'),
      import('@material/web/switch/switch.js'),
      import('@material/web/dialog/dialog.js'),
      import('@material/web/select/outlined-select.js'),
      import('@material/web/select/select-option.js'),
      import('@material/web/slider/slider.js'),
    ]).then(() => setState('ready')).catch((error) => setState(String(error)));
  }, []);
  return state;
}
interface TextFieldProps {
  label: string; value: string; onChange: (value: string) => void;
  type?: 'text' | 'url' | 'textarea'; rows?: number; disabled?: boolean;
  autocomplete?: string;
}
export function TextField({ onChange, ...props }: TextFieldProps) {
  return createElement('md-outlined-text-field', { ...props, 'aria-label': props.label,
    onInput: (event: Event) => onChange((event.target as HTMLInputElement).value) });
}
interface FieldProps {
  label: string; value: number; onChange: (value: number) => void;
  step?: string; min?: string; max?: string;
}
export function Field({ onChange, step = '1', min = '0', ...props }: FieldProps) {
  return createElement('md-outlined-text-field', { ...props, type: 'number', step, min,
    'aria-label': props.label, value: String(props.value),
    onInput: (event: Event) => onChange(Number((event.target as HTMLInputElement).value)) });
}
export function Switch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className='switch-row'><span>{label}</span>{createElement('md-switch', {
    selected: checked, 'aria-label': label,
    onChange: (event: Event) => onChange((event.target as HTMLElement & { selected: boolean }).selected),
  })}</label>;
}
export function Progress({ value, label }: { value?: number; label: string }) {
  return createElement('studio-linear-progress', { value, indeterminate: value === undefined, 'aria-label': label });
}
interface TabsProps { value: string; options: readonly string[]; onChange: (value: string) => void; label?: string }
export function Tabs({ value, options, onChange, label = '面板切换' }: TabsProps) {
  return createElement('md-tabs', { 'aria-label': label, autoActivate: true,
    onChange: (event: Event) => onChange(options[(event.target as HTMLElement & { activeTabIndex: number }).activeTabIndex]),
  }, options.map((name) => createElement('md-secondary-tab', { key: name, active: value === name }, name)));
}
interface SelectProps {
  label: string; value: string; options: readonly { value: string; label: string }[];
  onChange: (value: string) => void;
}
export function Select({ onChange, options, ...props }: SelectProps) {
  const reduced = useReducedMotion();
  return createElement('md-outlined-select', { ...props, quick: reduced, 'aria-label': props.label, menuPositioning: 'popover',
    onChange: (event: Event) => onChange((event.target as HTMLElement & { value: string }).value),
  }, options.map((option) => createElement('md-select-option', { key: option.value, value: option.value, selected: option.value === props.value },
    <span slot='headline'>{option.label}</span>)));
}
interface SliderProps { label: string; value: number; max: number; step?: number; disabled?: boolean; onChange: (value: number) => void }
export function Slider({ label, onChange, step = 1, ...props }: SliderProps) {
  return createElement('md-slider', { ...props, min: 0, step, 'aria-label': label,
    onInput: (event: Event) => onChange((event.target as HTMLElement & { value: number }).value),
  });
}
export function MaterialDialog({ open, title, children, onClose }: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLElement & { open: boolean; show: () => Promise<void>; close: () => Promise<void> }>(null);
  useEffect(() => {
    if (open && !ref.current?.open) void ref.current?.show();
    if (!open && ref.current?.open) void ref.current?.close();
  }, [open]);
  return createElement('md-dialog', { ref, oncancel: onClose, onclosed: onClose,
    getOpenAnimation: () => dialogAnimation({ opening: true, reduced }),
    getCloseAnimation: () => dialogAnimation({ opening: false, reduced }),
  },
    <div slot='headline'>{title}</div>, <div slot='content'>{children}</div>);
}
