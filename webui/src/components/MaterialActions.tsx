'use client';
import { useEffect, useRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes } from 'react';
import { buttonClasses, setupButton } from '@material/web/labs/gb/components/button/button.js';
import { iconButtonClasses, setupIconButton } from '@material/web/labs/gb/components/iconbutton/icon-button.js';
import { listItemClasses, setupListItem } from '@material/web/labs/gb/components/list/list.js';

type Variant = 'filled' | 'tonal' | 'outlined' | 'text';
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: Variant }
function classNames(classes: Record<string, unknown>) {
  return Object.entries(classes).filter(([, enabled]) => enabled).map(([name]) => name).join(' ');
}
function useBehavior<T extends HTMLElement>(kind: 'button' | 'icon' | 'list') {
  const ref = useRef<T>(null);
  useEffect(() => {
    const abort = new AbortController();
    if (ref.current) ({ button: setupButton, icon: setupIconButton, list: setupListItem })[kind](ref.current, { signal: abort.signal });
    return () => abort.abort();
  }, [kind]);
  return ref;
}
export function Button({ variant = 'tonal', className = '', ...props }: ButtonProps) {
  return <button ref={useBehavior<HTMLButtonElement>('button')} type='button' {...props}
    className={`${classNames(buttonClasses({ color: variant, size: 'sm' }))} ${className}`} />;
}
export function IconButton({ label, className = '', variant = 'text', ...props }: ButtonProps & { label: string }) {
  const color = variant === 'text' ? 'standard' : variant;
  return <button ref={useBehavior<HTMLButtonElement>('icon')} type='button' {...props} title={label} aria-label={label}
    className={`${classNames(iconButtonClasses({ color, size: 'sm' }))} ${className}`} />;
}
export function ListButton({ selected, className = '', ...props }: ButtonProps & { selected?: boolean }) {
  return <button ref={useBehavior<HTMLButtonElement>('list')} type='button' {...props} aria-current={selected || undefined}
    className={`${classNames(listItemClasses())} ${selected ? 'selected' : ''} ${className}`} />;
}
export function ActionLink({ variant = 'text', className = '', ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant }) {
  return <a ref={useBehavior<HTMLAnchorElement>('button')} {...props}
    className={`${classNames(buttonClasses({ color: variant, size: 'sm' }))} ${className}`} />;
}
