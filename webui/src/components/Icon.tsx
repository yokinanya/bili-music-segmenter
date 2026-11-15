import { icons } from '@/lib/iconGeometries';

export type IconName = keyof typeof icons;
export type IconSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

/**
 * Icons are sized only by the `--icon-size` token so every call site stays aligned.
 * The svg is larger than the drawable box (24 grid vs 20 drawable) and overflows
 * centered, so stroke extents stay optically centered at every size.
 */
export function Icon({ name, size = 'sm', className = '' }: { name: IconName; size?: IconSize; className?: string }) {
  const icon = icons[name];
  return <span className={`icon icon-${size} ${className}`.trim()} aria-hidden="true">
    <svg viewBox="0 0 24 24" fill={icon.filled ? 'currentColor' : 'none'}>
      <path d={icon.path} stroke={icon.filled ? 'none' : 'currentColor'} strokeWidth={icon.stroke}
        strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  </span>;
}
