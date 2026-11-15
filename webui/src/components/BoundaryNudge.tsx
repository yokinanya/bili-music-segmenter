'use client';
import { useState } from 'react';
import type { SongClip } from '@/lib/editor';
import { nudgeBoundary, type BoundaryEdge } from '@/lib/boundaryNudge';
import { errorText } from '@/lib/format';
import { Button } from './Material';

interface Props { clip: SongClip; duration: number; onChange: (clip: SongClip) => void; onLocate: (time: number) => void }
const STEPS = [0.01, 0.1, 1];

export function BoundaryNudge({ clip, duration, onChange, onLocate }: Props) {
  const [step, setStep] = useState(0.1), [error, setError] = useState('');
  const adjust = (edge: BoundaryEdge, delta: number) => {
    try { const revised = nudgeBoundary(clip, { edge, delta, duration }); onChange(revised); onLocate(revised[edge]); setError(''); }
    catch (cause) { setError(errorText(cause)); }
  };
  return <div className="boundary-nudge">
    <div className="boundary-steps" role="group" aria-label="微调步长">{STEPS.map(value => <Button key={value} variant={step === value ? 'tonal' : 'text'} aria-pressed={step === value} onClick={() => setStep(value)}>{value}秒</Button>)}</div>
    <div className="boundary-adjustments">{(['start_seconds', 'end_seconds'] as const).map(edge => {
      const label = edge === 'start_seconds' ? '开头' : '结尾';
      const before = Math.round((clip[edge] - step) * 1000) / 1000, after = Math.round((clip[edge] + step) * 1000) / 1000;
      return <div key={edge}><span>{label}</span>
        <Button variant="text" aria-label={`${label}前移`} disabled={edge === 'start_seconds' ? before < 0 : before <= clip.start_seconds} onClick={() => adjust(edge, -step)}>−{step}</Button>
        <Button variant="text" aria-label={`${label}后移`} disabled={edge === 'end_seconds' ? after > duration : after >= clip.end_seconds} onClick={() => adjust(edge, step)}>+{step}</Button>
      </div>;
    })}</div>
    {error && <p className="error" role="alert">{error}</p>}
  </div>;
}
