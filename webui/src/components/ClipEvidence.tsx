import { clipEvidence } from '@/lib/clipEvidence';
import type { Clip } from '@/lib/types';
import { Disclosure } from './Disclosure';

export function ClipEvidence({ clip }: { readonly clip: Clip }) {
  return <Disclosure title="识曲依据">
    <dl className="clip-evidence-summary">
      {clipEvidence(clip.recognition, clip.title_resolution).map((row, index) =>
        <div key={`${row.label}-${index}`}><dt>{row.label}</dt><dd>{row.text}</dd></div>)}
    </dl>
    <Disclosure title="原始记录 JSON">
      <pre className="clip-evidence">{JSON.stringify({ recognition: clip.recognition, title_resolution: clip.title_resolution }, null, 2)}</pre>
    </Disclosure>
  </Disclosure>;
}
