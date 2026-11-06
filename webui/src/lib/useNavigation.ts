'use client';
import { useCallback, useEffect, useState } from 'react';

const DEFAULTS = { page: '工作台', view: '导入与设置', source: '本地文件', history: '', historyView: '队列与进度', output: '结果', job: '', query: '', status: 'all', usage: '' };
export type NavigationState = typeof DEFAULTS;
function read(): NavigationState {
  if (typeof window === 'undefined') return DEFAULTS;
  const query = new URLSearchParams(window.location.search);
  return Object.fromEntries(Object.entries(DEFAULTS).map(([key, value]) => [key, query.get(key) ?? value])) as NavigationState;
}
export function useNavigation() {
  const [navigation, setNavigation] = useState(DEFAULTS);
  useEffect(() => {
    const restore = () => setNavigation(read());
    restore(); window.addEventListener('popstate', restore); window.addEventListener('bms-navigation', restore);
    return () => { window.removeEventListener('popstate', restore); window.removeEventListener('bms-navigation', restore); };
  }, []);
  const navigate = useCallback((changes: Partial<NavigationState>) => {
    const next = { ...read(), ...changes };
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(next)) {
      if (value === DEFAULTS[key as keyof NavigationState]) url.searchParams.delete(key);
      else url.searchParams.set(key, value);
    }
    window.history.pushState(null, '', url.pathname + url.search + url.hash);
    setNavigation(next); window.dispatchEvent(new Event('bms-navigation'));
  }, []);
  return { navigation, navigate };
}
