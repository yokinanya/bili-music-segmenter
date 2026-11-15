export const PAGES = ['工作台', '链接下载', '用量', '设置'] as const;
export type Page = (typeof PAGES)[number];

export interface Navigation {
  readonly page: Page;
  readonly view: string;
  readonly source: string;
  readonly usage: string;
  readonly output: string;
}

export const DEFAULT_NAVIGATION: Navigation = { page: '工作台', view: '导入与设置', source: '本地文件', usage: '', output: '' };

const isPage = (value: string | null): value is Page => !!value && (PAGES as readonly string[]).includes(value);

/**
 * URL is the only navigation state. Unknown or retired values (for example the removed
 * history page) fall back to defaults so a stale bookmark never renders an empty view.
 */
export function parseNavigation(search: string): Navigation {
  const query = new URLSearchParams(search);
  const page = query.get('page');
  return {
    page: isPage(page) ? page : DEFAULT_NAVIGATION.page,
    view: query.get('view') ?? DEFAULT_NAVIGATION.view,
    source: query.get('source') ?? DEFAULT_NAVIGATION.source,
    usage: query.get('usage') ?? DEFAULT_NAVIGATION.usage,
    output: query.get('output') ?? DEFAULT_NAVIGATION.output,
  };
}

export function serializeNavigation(next: Partial<Navigation>, current: Navigation = DEFAULT_NAVIGATION): string {
  const merged = { ...current, ...next };
  const query = new URLSearchParams();
  for (const key of Object.keys(DEFAULT_NAVIGATION) as (keyof Navigation)[]) {
    if (merged[key] !== DEFAULT_NAVIGATION[key]) query.set(key, merged[key]);
  }
  return query.toString();
}
