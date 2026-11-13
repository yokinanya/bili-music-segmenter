function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

export interface TitleCandidate {
  readonly title: string;
  readonly artist: string;
  readonly sources: readonly string[];
}

const PROVIDERS: readonly [string, string][] = [['shazam', 'Shazam'], ['netease', '网易云']];

// 只处理常见繁简差异；与后端 OpenCC 归一化方向一致，保证同一首歌只出一个候选。
const TRADITIONAL_TO_SIMPLIFIED: Readonly<Record<string, string>> = {
  絕: '绝', 愛: '爱', 為: '为', 風: '风', 韻: '韵', 語: '语', 間: '间', 認: '认', 誰: '谁', 難: '难',
  過: '过', 門: '门', 開: '开', 時: '时', 說: '说', 東: '东', 聽: '听', 處: '处', 這: '这', 樣: '样',
  裡: '里', 兒: '儿', 點: '点', 經: '经', 還: '还', 個: '个', 們: '们', 來: '来', 問: '问', 當: '当',
  給: '给', 興: '兴', 對: '对', 動: '动', 態: '态', 熱: '热', 見: '见', 話: '话', 讓: '让', 麼: '么',
};

function toSimplified(title: string): string {
  return [...title].map((char) => TRADITIONAL_TO_SIMPLIFIED[char] ?? char).join('');
}

function key(title: string): string {
  return toSimplified(title).replace(/[\s（）()【】[\]<>《》]/g, '').toLowerCase();
}

/** 冲突时把各家歌名整理成可点选的候选；歌名相同视为同一候选，歌手只作参考。 */
export function titleCandidates(recognition: unknown, resolution: unknown): readonly TitleCandidate[] {
  const sources = record(recognition);
  const matched = PROVIDERS.flatMap(([name, label]) => {
    const source = record(sources[name]);
    const title = typeof source.title === 'string' ? source.title.trim() : '';
    if (source.status !== 'matched' || !title) return [];
    return [{ label, title, artist: typeof source.artist === 'string' ? source.artist.trim() : '' }];
  });
  const chosen = record(resolution).status === 'matched' ? matched[0]?.title : '';
  const rows = new Map<string, { title: string; artist: string; sources: string[] }>();
  for (const item of matched) {
    const identity = key(item.title);
    const existing = rows.get(identity);
    if (existing) {
      existing.sources.push(item.label);
      if (!existing.artist) existing.artist = item.artist;
      continue;
    }
    // 同一首作品优先展示简体标题，与后端 OpenCC 归一化的选择保持一致。
    const display = chosen && key(chosen) === identity ? chosen : item.title;
    rows.set(identity, { title: toSimplified(display), artist: item.artist, sources: [item.label] });
  }
  return [...rows.values()];
}
