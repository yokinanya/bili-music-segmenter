'use client';
import { useId, useState, type ReactNode } from 'react';
import { Button } from './Material';
import { Icon } from './Icon';

export function Disclosure({ title, children, defaultOpen = false, className = '' }: {
  title: string; children: ReactNode; defaultOpen?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return <div className={`disclosure ${className}`}>
    <Button variant='text' className='disclosure-trigger' aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
      <span>{title}</span><span className={`disclosure-icon ${open ? 'expanded' : ''}`}><Icon name='down' /></span>
    </Button>
    <div id={id} className='disclosure-content' hidden={!open}>{children}</div>
  </div>;
}
