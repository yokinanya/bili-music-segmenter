import fs from 'node:fs';
import { themeFromSourceColor } from '../node_modules/@material/material-color-utilities/utils/theme_utils.js';
import { argbFromHex, hexFromArgb } from '../node_modules/@material/material-color-utilities/utils/string_utils.js';
const theme = themeFromSourceColor(argbFromHex('#3f5ad4'));
let css = '/* Generated from #3f5ad4 with Material color utilities. */\n';
for (const [name, scheme] of Object.entries(theme.schemes)) {
  css += `${name === 'light' ? ':root' : ':root[data-theme="dark"]'}{color-scheme:${name};\n`;
  for (const [key, value] of Object.entries(scheme.toJSON())) css += `--md-sys-color-${key.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}:${hexFromArgb(value)};\n`;
  const tones = name === 'light' ? { lowest: 100, low: 96, normal: 94, high: 92, highest: 90 } : { lowest: 4, low: 10, normal: 12, high: 17, highest: 22 };
  for (const [key, tone] of Object.entries(tones)) css += `--md-sys-color-surface-container${key === 'normal' ? '' : '-' + key}:${hexFromArgb(theme.palettes.neutral.tone(tone))};\n`;
  css += name === 'light' ? '--success:#276648;--success-container:#ddf2e4;\n' : '--success:#9ad5af;--success-container:#193d2b;\n';
  css += '}\n';
}
css += ':root{--md-ref-typeface-plain:"Roboto Flex",sans-serif;--md-ref-typeface-brand:"Roboto Flex",sans-serif;--md-sys-typescale-label-lg:500 14px/20px "Roboto Flex",sans-serif;--md-sys-typescale-body-lg:400 14px/20px "Roboto Flex",sans-serif}\n';
fs.writeFileSync(new URL('../src/app/theme.css', import.meta.url), css);
