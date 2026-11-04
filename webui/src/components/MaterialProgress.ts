import { MdLinearProgress } from '@material/web/progress/linear-progress.js';

const motion = new CSSStyleSheet();
motion.replaceSync(`
  .bar, .inactive-track { transition-duration: 150ms; }
  @media (prefers-reduced-motion: reduce) {
    .bar, .inactive-track { transition: none; }
    .bar, .bar-inner, .dots { animation: none !important; }
  }
`);
class StudioLinearProgress extends MdLinearProgress {
  static override styles = [...MdLinearProgress.styles, motion];
}
customElements.define('studio-linear-progress', StudioLinearProgress);
