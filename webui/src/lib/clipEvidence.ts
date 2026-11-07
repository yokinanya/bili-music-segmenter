export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

const statuses: Record<string, string> = {
  matched: '已匹配', no_match: '未匹配', disabled: '未启用', error: '请求失败',
  unmatched: '未识别', unresolved: '未确认', single_provider: '单一来源识别',
  conflict: '结果有冲突', qwen_resolved: '文本复核确认', audio_verified: '音频复核确认',
  qqmusic_verified: 'QQ 音乐歌词核对通过', qqmusic_conflict: 'QQ 音乐与识曲结果有冲突',
  insufficient_evidence: '歌词证据不足', ambiguous: '存在多个作品候选', manual: '人工确认',
};

export interface EvidenceRow { readonly label: string; readonly text: string }

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function status(value: unknown): string {
  return statuses[text(value)] || text(value) || '未记录';
}

function reviewRows(name: string, value: unknown): EvidenceRow[] {
  const review = record(value);
  const data = record(review.data ?? value);
  const rows: EvidenceRow[] = [];
  if (typeof data.confidence === 'number') rows.push({ label: `${name}置信度`, text: `${Math.round(data.confidence * 100)}%` });
  for (const [key, label] of Object.entries({ language: '演唱语言', lyrics_evidence: '实听歌词', name_evidence: '名称依据', rationale: `${name}依据` })) {
    if (text(data[key])) rows.push({ label, text: text(data[key]) });
  }
  return rows;
}

export function clipEvidence(recognition: unknown, resolution: unknown): EvidenceRow[] {
  const sources = record(recognition);
  const result = record(resolution);
  const rows: EvidenceRow[] = [{ label: '标题结论', text: status(result.status) }];
  for (const [key, label] of Object.entries({ shazam: 'Shazam', netease: '网易云' })) {
    const source = record(sources[key]);
    if (!Object.keys(source).length) continue;
    const song = [text(source.title), text(source.artist)].filter(Boolean).join(' · ');
    rows.push({ label, text: [status(source.status), song, text(source.error)].filter(Boolean).join(' · ') });
  }
  rows.push(...reviewRows('文本复核', result.text), ...reviewRows('音频复核', result.audio));
  const qq = record(result.qqmusic);
  if (Object.keys(qq).length) {
    rows.push({ label: 'QQ 音乐歌词核对', text: [status(qq.status), text(qq.title), text(qq.artist)].filter(Boolean).join(' · ') });
    if (text(qq.query)) rows.push({ label: '检索歌词', text: text(qq.query) });
    if (text(qq.reason)) rows.push({ label: '核对说明', text: text(qq.reason) });
    if (text(qq.mid)) rows.push({ label: 'QQ 音乐歌曲 MID', text: text(qq.mid) });
    if (Array.isArray(qq.candidates)) rows.push({ label: '歌词匹配候选', text: qq.candidates.map(value => {
      const song = record(value);
      return [text(song.title), text(song.artist)].filter(Boolean).join(' · ');
    }).join('\n') || '无' });
  }
  const manual = record(result.manual);
  if (text(manual.reason)) rows.push({ label: '人工修订依据', text: text(manual.reason) });
  return rows;
}
