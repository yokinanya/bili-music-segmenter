'use client';

import { useCallback, useEffect, useState } from 'react';

type Theme = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'bms-theme';
const ORDER: Theme[] = ['system', 'light', 'dark'];
const LABELS: Record<Theme, string> = { system: '跟随系统', light: '浅色', dark: '深色' };
const ICONS: Record<Theme, string> = { system: '◐', light: '☀', dark: '☾' };

function applyTheme(theme: Theme) {
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system');

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
    const initial = stored && ORDER.includes(stored) ? stored : 'system';
    setTheme(initial);
    applyTheme(initial);
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if ((window.localStorage.getItem(STORAGE_KEY) as Theme | null) === 'system' || !window.localStorage.getItem(STORAGE_KEY)) {
        applyTheme('system');
      }
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const cycle = useCallback(() => {
    setTheme((current) => {
      const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
      window.localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
      return next;
    });
  }, []);

  return (
    <button type="button" className="theme-toggle" onClick={cycle} title={`主题：${LABELS[theme]}（点击切换）`}>
      <span aria-hidden="true">{ICONS[theme]}</span>
      <span className="visually-hidden">当前主题 {LABELS[theme]}，点击切换</span>
    </button>
  );
}
