'use client';
import { useCallback, useEffect, useState } from 'react';
import { DEFAULT_NAVIGATION, parseNavigation, serializeNavigation, type Navigation } from './navigation';

/**
 * URL is the single source of navigation state. The hook keeps a shadow copy only to
 * re-render, and always re-parses the URL so back/forward stays authoritative.
 */
export function useNavigation() {
  const [navigation, setNavigation] = useState<Navigation>(DEFAULT_NAVIGATION);
  useEffect(() => {
    const restore = () => setNavigation(parseNavigation(window.location.search));
    restore();
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  const navigate = useCallback((changes: Partial<Navigation>) => {
    const next = parseNavigation(serializeNavigation(changes, parseNavigation(window.location.search)));
    const query = serializeNavigation(next);
    const url = new URL(window.location.href);
    url.search = query;
    window.history.pushState(null, '', url.pathname + url.search + url.hash);
    setNavigation(next);
  }, []);
  return { navigation, navigate };
}
