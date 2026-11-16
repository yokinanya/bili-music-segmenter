'use client';
import { useState } from 'react';
import type { SongClip } from '@/lib/editor';
import { nudgeBoundary, type BoundaryEdge } from '@/lib/boundaryNudge';
import { errorText } from '@/lib/format';
import { Button } from './Material';
import { Icon } from './Icon';

interface Props { clip: SongClip; duration: number; onChange: (clip: SongClip) => void; onLocate: (time: number) => void }
const STEPS = [0.01, 0.1, 1];

export function BoundaryNudge({ clip, duration, onChange, onLocate }: Props) {
  const [step, setStep] = useState(0.1), [error, setError] = useState('');
  const [edge, setEdge] = useState<BoundaryEdge>('start_seconds');
  const label = edge === 'start_seconds' ? '开头' : '结尾';
  const before = Math.round((clip[edge] - step) * 1000) / 1000;
  const after = Math.round((clip[edge] + step) * 1000) / 1000;
  const nextStep = STEPS[(STEPS.indexOf(step) + 1) % STEPS.length];
  const adjust = (edge: BoundaryEdge, delta: number) => {
    try { const revised = nudgeBoundary(clip, { edge, delta, duration }); onChange(revised); onLocate(revised[edge]); setError(''); }
    catch (cause) { setError(errorText(cause)); }
  };
  return <div className="boundary-nudge">
    <div className="boundary-steps">
      <Button className="boundary-step-cycle" variant="tonal" aria-label={`当前微调步长 ${step} 秒，点击切换为 ${nextStep} 秒`}
        title="循环切换步长：0.01 / 0.1 / 1 秒" onClick={() => setStep(nextStep)}>
        <span>步长</span><span className="boundary-step-value" aria-live="polite">{step} 秒</span><Icon name="retry" size="xs" />
      </Button>
    </div>
    <div className="boundary-adjustments"><div>
        <Button variant="tonal" aria-label={`当前微调${label}，点击切换${edge === 'start_seconds' ? '结尾' : '开头'}`}
          onClick={() => setEdge(value => value === 'start_seconds' ? 'end_seconds' : 'start_seconds')}>{label}<Icon name="retry" size="xs" /></Button>
        <Button variant="text" aria-label={`${label}前移`} disabled={edge === 'start_seconds' ? before < 0 : before <= clip.start_seconds} onClick={() => adjust(edge, -step)}>−{step}</Button>
        <Button variant="text" aria-label={`${label}后移`} disabled={edge === 'end_seconds' ? after > duration : after >= clip.end_seconds} onClick={() => adjust(edge, step)}>+{step}</Button>
      </div></div>
    {error && <p className="error" role="alert">{error}</p>}
  </div>;
}
